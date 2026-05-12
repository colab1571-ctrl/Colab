"""
invite-svc — Celery Beat TTL archival task.

expire_stale_invites:
  - Runs hourly (cron 0 * * * *)
  - Finds pending invites where archive_at <= NOW()
  - Batch-updates status=expired in chunks of 500
  - Publishes invite.expired events to RabbitMQ
  - Idempotent: already-expired rows not re-processed (WHERE clause filters)
  - acks_late=True + max_retries=3 (exponential backoff) for transient DB failures

NOTE: This task uses synchronous SQLAlchemy + aio_pika via a nested event loop
because Celery workers run in a synchronous context. In production, consider
Celery 5's asyncio support or a dedicated async worker.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import aio_pika
from celery import Task
from celery.utils.log import get_task_logger
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)
_BATCH_SIZE = 500


async def _expire_batch(db: AsyncSession, channel: aio_pika.abc.AbstractChannel) -> int:
    """Expire one batch of up to _BATCH_SIZE stale invites. Returns count updated."""
    from app.models.invite import CollabInvite

    now = datetime.now(tz=timezone.utc)

    # Fetch IDs in batch
    result = await db.execute(
        select(CollabInvite.id, CollabInvite.from_profile_id, CollabInvite.to_profile_id)
        .where(
            and_(
                CollabInvite.status == "pending",
                CollabInvite.archive_at <= now,
            )
        )
        .limit(_BATCH_SIZE)
        .with_for_update(skip_locked=True)
    )
    rows = result.all()
    if not rows:
        return 0

    ids = [r[0] for r in rows]

    # Bulk update
    await db.execute(
        update(CollabInvite)
        .where(CollabInvite.id.in_(ids))
        .values(status="expired", responded_at=now)
    )
    await db.commit()

    # Publish invite.expired events
    exchange = await channel.declare_exchange(
        "colab.events", aio_pika.ExchangeType.TOPIC, durable=True
    )
    for invite_id, from_id, to_id in rows:
        payload = {
            "event": "invite.expired",
            "invite_id": str(invite_id),
            "from_profile_id": str(from_id),
            "to_profile_id": str(to_id),
            "expired_at": now.isoformat(),
        }
        msg = aio_pika.Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await exchange.publish(msg, routing_key="invite.expired")

    logger.info("Expired %d stale invites", len(ids))
    return len(ids)


async def _run_expire_all(settings) -> int:
    """Run expiry in batches until no more stale invites."""
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    total = 0

    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        while True:
            async with session_factory() as db:
                count = await _expire_batch(db, channel)
            total += count
            if count < _BATCH_SIZE:
                break

    await engine.dispose()
    return total


@celery_app.task(
    name="app.workers.ttl_tasks.expire_stale_invites",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def expire_stale_invites(self: Task) -> dict:
    """
    Hourly job: flip pending invites past archive_at to expired.
    Idempotent — safe to re-run. Processes in batches of 500 with SKIP LOCKED.
    """
    settings = get_settings()
    try:
        total = asyncio.run(_run_expire_all(settings))
        logger.info("expire_stale_invites completed: %d invites expired", total)
        return {"status": "ok", "expired_count": total}
    except Exception as exc:
        logger.exception("expire_stale_invites failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
