"""
Celery task: hourly inactivity check.

- 14-day nudge (once per inactivity window)
- 30-day auto-archive (non-terminal collabs)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from celery import shared_task
from sqlalchemy import and_, or_, select, update

from app.config import get_collab_settings
from app.db import AsyncSessionLocal
from app.models import Collaboration
from app.workers.archive_tasks import archive_collab
from app.workers.events import emit_event

logger = logging.getLogger(__name__)
settings = get_collab_settings()


def _run_async(coro):  # type: ignore[no-untyped-def]
    """Run coroutine in a new event loop (Celery worker context)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(name="app.workers.inactivity_tasks.inactivity_check", bind=True)
def inactivity_check(self) -> dict:  # type: ignore[no-untyped-def]
    """Hourly Celery Beat task: scan for stale collabs, dispatch nudge/archive subtasks."""
    return _run_async(_inactivity_check_async())


async def _inactivity_check_async() -> dict:
    now = datetime.now(UTC)
    nudge_threshold = now - timedelta(days=settings.nudge_days)
    archive_threshold = now - timedelta(days=settings.archive_days)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Collaboration).where(
                and_(
                    Collaboration.status.in_(["still_deciding", "in_progress"]),
                    Collaboration.archived_at.is_(None),
                    or_(
                        and_(
                            Collaboration.last_activity_at < nudge_threshold,
                            Collaboration.nudge_sent_at.is_(None),
                        ),
                        Collaboration.last_activity_at < archive_threshold,
                    ),
                )
            )
        )
        collabs = result.scalars().all()

    nudge_count = 0
    archive_count = 0

    for c in collabs:
        if c.last_activity_at < archive_threshold:
            # Dispatch archive subtask
            archive_collab.delay(str(c.id))
            archive_count += 1
        elif c.last_activity_at < nudge_threshold and c.nudge_sent_at is None:
            # Dispatch nudge subtask
            send_nudge.delay(str(c.id))
            nudge_count += 1

    logger.info(
        "inactivity_check: %d nudges dispatched, %d archives dispatched",
        nudge_count,
        archive_count,
    )
    return {"nudges": nudge_count, "archives": archive_count}


@shared_task(name="app.workers.inactivity_tasks.send_nudge", bind=True)
def send_nudge(self, collab_id_str: str) -> None:  # type: ignore[no-untyped-def]
    _run_async(_send_nudge_async(collab_id_str))


async def _send_nudge_async(collab_id_str: str) -> None:
    collab_id = uuid.UUID(collab_id_str)
    now = datetime.now(UTC)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Collaboration).where(
                Collaboration.id == collab_id,
                Collaboration.nudge_sent_at.is_(None),
                Collaboration.archived_at.is_(None),
            )
        )
        collab = result.scalars().first()
        if collab is None:
            logger.info("Nudge skipped (already nudged or archived): %s", collab_id_str)
            return

        await db.execute(
            update(Collaboration)
            .where(Collaboration.id == collab_id, Collaboration.nudge_sent_at.is_(None))
            .values(nudge_sent_at=now)
        )
        await db.commit()

        # Emit event for notification-svc
        await emit_event(
            "collab.nudge_due",
            {
                "collab_id": str(collab_id),
                "profile_id_a": str(collab.profile_id_a),
                "profile_id_b": str(collab.profile_id_b),
            },
        )
        logger.info("Nudge emitted for collab %s", collab_id_str)
