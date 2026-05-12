"""
RabbitMQ event consumers for collab-svc.

Consumed events:
- match.created       → create Collaboration
- chat.message.sent   → update last_activity_at
- block.created       → flip is_read_only + archive_at
- chat.media.scanned  → upsert CollabFileName (search denorm)
- profile.display_name_changed → refresh name cache + search_vector
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import AsyncGenerator

import aio_pika
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_collab_settings
from app.db import AsyncSessionLocal
from app.models import Collaboration, CollabFileName
from app.services.collab_service import (
    apply_block,
    create_collaboration,
    update_last_activity,
    upsert_name_cache,
)
from app.workers.events import emit_event

logger = logging.getLogger(__name__)
settings = get_collab_settings()


async def start_consumers() -> None:
    """Start all RabbitMQ consumers. Called from FastAPI lifespan."""
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)

    exchange = await channel.declare_exchange(
        "colab.events", aio_pika.ExchangeType.TOPIC, durable=True
    )

    # Declare queues and bind
    queue_map = {
        "collab-svc.match.created": "match.created",
        "collab-svc.chat.message.sent": "chat.message.sent",
        "collab-svc.block.created": "block.created",
        "collab-svc.chat.media.scanned": "chat.media.scanned",
        "collab-svc.profile.display_name_changed": "profile.display_name_changed",
    }

    handler_map = {
        "match.created": _handle_match_created,
        "chat.message.sent": _handle_chat_message_sent,
        "block.created": _handle_block_created,
        "chat.media.scanned": _handle_chat_media_scanned,
        "profile.display_name_changed": _handle_display_name_changed,
    }

    for queue_name, routing_key in queue_map.items():
        queue = await channel.declare_queue(queue_name, durable=True)
        await queue.bind(exchange, routing_key=routing_key)

        async def make_consumer(rk: str):  # type: ignore[no-untyped-def]
            handler = handler_map[rk]

            async def on_message(message: aio_pika.IncomingMessage) -> None:
                async with message.process(requeue=True):
                    try:
                        payload = json.loads(message.body.decode())
                        await handler(payload)
                    except Exception as exc:
                        logger.exception("Error handling %s: %s", rk, exc)
                        raise

            return on_message

        consumer = await make_consumer(routing_key)
        await queue.consume(consumer)

    logger.info("collab-svc consumers started")
    # Keep running
    await asyncio.Future()


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _handle_match_created(payload: dict) -> None:
    """match.created → create Collaboration + emit collab.created."""
    profile_id_a = uuid.UUID(payload["profile_id_a"])
    profile_id_b = uuid.UUID(payload["profile_id_b"])
    match_id = uuid.UUID(payload.get("match_id", str(uuid.uuid4())))

    async with AsyncSessionLocal() as db:
        collab = await create_collaboration(db, profile_id_a, profile_id_b, match_id)

    await emit_event(
        "collab.created",
        {
            "collab_id": str(collab.id),
            "profile_id_a": str(profile_id_a),
            "profile_id_b": str(profile_id_b),
            "match_id": str(match_id),
        },
    )
    logger.info("Collaboration %s created from match %s", collab.id, match_id)


async def _handle_chat_message_sent(payload: dict) -> None:
    """chat.message.sent → update last_activity_at + clear nudge_sent_at."""
    collab_id_str = payload.get("collaboration_id") or payload.get("collab_id")
    if not collab_id_str:
        return
    collab_id = uuid.UUID(collab_id_str)
    sent_at_str = payload.get("sent_at") or payload.get("created_at")
    sent_at = (
        datetime.fromisoformat(sent_at_str) if sent_at_str else datetime.now(UTC)
    )

    async with AsyncSessionLocal() as db:
        await update_last_activity(db, collab_id, sent_at)


async def _handle_block_created(payload: dict) -> None:
    """block.created → flip collab to read-only + deferred archive."""
    blocker_id = uuid.UUID(payload["blocker_profile_id"])
    blocked_id = uuid.UUID(payload["blocked_profile_id"])

    async with AsyncSessionLocal() as db:
        await apply_block(db, blocker_id, blocked_id)
    logger.info("Block applied: %s -> %s", blocker_id, blocked_id)


async def _handle_chat_media_scanned(payload: dict) -> None:
    """chat.media.scanned → insert CollabFileName for FTS denorm."""
    collab_id_str = payload.get("collaboration_id") or payload.get("collab_id")
    s3_key = payload.get("s3_key", "")
    file_name = payload.get("file_name") or s3_key.split("/")[-1]
    if not collab_id_str or not s3_key:
        return

    collab_id = uuid.UUID(collab_id_str)

    async with AsyncSessionLocal() as db:
        stmt = (
            pg_insert(CollabFileName)
            .values(collab_id=collab_id, s3_key=s3_key, file_name=file_name)
            .on_conflict_do_nothing()
        )
        await db.execute(stmt)
        await db.commit()
        # Refresh search vector
        await db.execute(
            text("SELECT collab.refresh_search_vector(:cid)").bindparams(cid=str(collab_id))
        )
        await db.commit()


async def _handle_display_name_changed(payload: dict) -> None:
    """profile.display_name_changed → refresh name cache + search_vectors."""
    profile_id = uuid.UUID(payload["profile_id"])
    display_name = payload["display_name"]

    async with AsyncSessionLocal() as db:
        # Find all collabs for this profile
        result = await db.execute(
            select(Collaboration).where(
                (Collaboration.profile_id_a == profile_id)
                | (Collaboration.profile_id_b == profile_id)
            )
        )
        collabs = result.scalars().all()

        for collab in collabs:
            await upsert_name_cache(db, collab.id, profile_id, display_name)
