"""
chat-svc RabbitMQ event consumers.

Subscribed events:
- match.created    → create chat_room row
- block.created    → set room state=read_only; broadcast room_state WS frame
- block.removed    → if room < 30d old, set state=open; broadcast

These run as a standalone asyncio loop launched from a separate entrypoint
(or from lifespan) — one aio-pika consumer per pod.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import aio_pika
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import _get_session_factory
from app.models import ChatRoom
from app.schemas import ws_room_state
from app.uuidv7 import generate_uuidv7

logger = logging.getLogger(__name__)

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://colab:colab@localhost:5672/")


async def _get_db_session() -> AsyncSession:
    return _get_session_factory()()


async def _handle_match_created(payload: dict) -> None:
    """Create ChatRoom on match.created event."""
    collab_id = uuid.UUID(payload["collaboration_id"])
    profile_a = uuid.UUID(payload["profile_id_a"])
    profile_b = uuid.UUID(payload["profile_id_b"])

    async with _get_session_factory()() as db:
        # Idempotency: check if room already exists for this collab
        result = await db.execute(
            select(ChatRoom).where(ChatRoom.collaboration_id == collab_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            logger.info("ChatRoom already exists for collab %s", collab_id)
            return

        room = ChatRoom(
            id=generate_uuidv7(),
            collaboration_id=collab_id,
            participant_ids=[profile_a, profile_b],
            state="open",
            created_at=datetime.now(tz=timezone.utc),
        )
        db.add(room)
        await db.commit()
        logger.info("Created ChatRoom %s for collab %s", room.id, collab_id)

        # Publish collab.created event for collab-svc
        await _emit_collab_created(collab_id, room.id)


async def _emit_collab_created(collab_id: uuid.UUID, room_id: uuid.UUID) -> None:
    try:
        conn = await aio_pika.connect_robust(RABBITMQ_URL)
        async with conn:
            channel = await conn.channel()
            exchange = await channel.declare_exchange("chat", aio_pika.ExchangeType.TOPIC)
            await exchange.publish(
                aio_pika.Message(
                    body=json.dumps({
                        "event": "chat.room.created",
                        "collaboration_id": str(collab_id),
                        "room_id": str(room_id),
                    }).encode()
                ),
                routing_key="chat.room.created",
            )
    except Exception as exc:
        logger.warning("Failed to emit chat.room.created: %s", exc)


async def _handle_block_created(payload: dict, presence_manager=None) -> None:
    """Set room to read_only when block.created fires."""
    profile_a = uuid.UUID(payload["blocker_profile_id"])
    profile_b = uuid.UUID(payload["blocked_profile_id"])

    async with _get_session_factory()() as db:
        result = await db.execute(
            text("""
                SELECT id, state, created_at FROM chat.chat_room
                WHERE :profile_a = ANY(participant_ids)
                  AND :profile_b = ANY(participant_ids)
                  AND state = 'open'
                LIMIT 1
            """),
            {"profile_a": profile_a, "profile_b": profile_b},
        )
        room_row = result.fetchone()
        if not room_row:
            return

        await db.execute(
            text("UPDATE chat.chat_room SET state = 'read_only' WHERE id = :id"),
            {"id": room_row.id},
        )
        await db.commit()
        logger.info("Room %s flipped to read_only due to block", room_row.id)

        # Publish room_state update via Redis (if presence_manager available)
        if presence_manager:
            await presence_manager.publish(
                uuid.UUID(str(room_row.id)), ws_room_state("read_only")
            )


async def _handle_block_removed(payload: dict, presence_manager=None) -> None:
    """Restore room to open if block removed and room not yet 30d old."""
    profile_a = uuid.UUID(payload["blocker_profile_id"])
    profile_b = uuid.UUID(payload["blocked_profile_id"])
    threshold = datetime.now(tz=timezone.utc) - timedelta(days=30)

    async with _get_session_factory()() as db:
        result = await db.execute(
            text("""
                SELECT id, state, created_at FROM chat.chat_room
                WHERE :profile_a = ANY(participant_ids)
                  AND :profile_b = ANY(participant_ids)
                  AND state = 'read_only'
                LIMIT 1
            """),
            {"profile_a": profile_a, "profile_b": profile_b},
        )
        room_row = result.fetchone()
        if not room_row:
            return

        # Only re-open if not yet archived-eligible (< 30d old)
        if room_row.created_at >= threshold:
            await db.execute(
                text("UPDATE chat.chat_room SET state = 'open' WHERE id = :id"),
                {"id": room_row.id},
            )
            await db.commit()
            logger.info("Room %s re-opened after block.removed", room_row.id)
            if presence_manager:
                await presence_manager.publish(
                    uuid.UUID(str(room_row.id)), ws_room_state("open")
                )


async def start_consumers(presence_manager=None) -> None:
    """Connect to RabbitMQ and start consuming events. Runs indefinitely."""
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)

    # Declare exchanges
    invite_exchange = await channel.declare_exchange(
        "invite", aio_pika.ExchangeType.TOPIC, durable=True
    )
    profile_exchange = await channel.declare_exchange(
        "profile", aio_pika.ExchangeType.TOPIC, durable=True
    )

    # match.created queue
    match_queue = await channel.declare_queue(
        "chat-svc.match.created", durable=True
    )
    await match_queue.bind(invite_exchange, routing_key="match.created")

    # block.created queue
    block_created_queue = await channel.declare_queue(
        "chat-svc.block.created", durable=True
    )
    await block_created_queue.bind(profile_exchange, routing_key="block.created")

    # block.removed queue
    block_removed_queue = await channel.declare_queue(
        "chat-svc.block.removed", durable=True
    )
    await block_removed_queue.bind(profile_exchange, routing_key="block.removed")

    async def on_match_created(message: aio_pika.IncomingMessage) -> None:
        async with message.process():
            try:
                payload = json.loads(message.body)
                await _handle_match_created(payload)
            except Exception as exc:
                logger.error("Error handling match.created: %s", exc, exc_info=True)

    async def on_block_created(message: aio_pika.IncomingMessage) -> None:
        async with message.process():
            try:
                payload = json.loads(message.body)
                await _handle_block_created(payload, presence_manager)
            except Exception as exc:
                logger.error("Error handling block.created: %s", exc, exc_info=True)

    async def on_block_removed(message: aio_pika.IncomingMessage) -> None:
        async with message.process():
            try:
                payload = json.loads(message.body)
                await _handle_block_removed(payload, presence_manager)
            except Exception as exc:
                logger.error("Error handling block.removed: %s", exc, exc_info=True)

    await match_queue.consume(on_match_created)
    await block_created_queue.consume(on_block_created)
    await block_removed_queue.consume(on_block_removed)

    logger.info("chat-svc event consumers started")
    # Block indefinitely
    await asyncio.Future()
