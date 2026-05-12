"""
colab_common.events — RabbitMQ async publish via aio-pika + outbox pattern helper.

Exchange naming convention: <domain>.<event_name>
e.g., "auth.user_signed_up", "profile.updated", "chat.message_sent"
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import aio_pika
import redis.asyncio as aioredis
from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from colab_common.db import Base
from colab_common.settings import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Outbox ORM model (services that use this must include it in their migration)
# ---------------------------------------------------------------------------


class EventOutbox(Base):
    """
    Outbox table for reliable event publishing.
    The relay worker drains this table and publishes to RabbitMQ.
    """

    __tablename__ = "event_outbox"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    event_name = Column(String(255), nullable=False, index=True)
    payload = Column(Text, nullable=False)
    dedupe_key = Column(String(512), nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    failed_attempts = Column(String(10), default="0")


# ---------------------------------------------------------------------------
# Connection helpers (lazy, shared per-process)
# ---------------------------------------------------------------------------

_connection: aio_pika.abc.AbstractConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None
_redis_client: aioredis.Redis | None = None  # type: ignore[type-arg]


async def _get_channel() -> aio_pika.abc.AbstractChannel:
    global _connection, _channel
    if _channel is None or _channel.is_closed:
        settings = get_settings()
        _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        _channel = await _connection.channel()
    return _channel


def _get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(settings.redis.url, decode_responses=True)
    return _redis_client


# ---------------------------------------------------------------------------
# Publish API
# ---------------------------------------------------------------------------


async def publish(
    event_name: str,
    payload: dict[str, Any],
    *,
    dedupe_key: str | None = None,
    exchange_name: str | None = None,
) -> bool:
    """
    Publish an event to RabbitMQ topic exchange.

    Args:
        event_name: e.g. "auth.user_signed_up"
        payload: Dict serializable to JSON.
        dedupe_key: If provided, SETNX in Redis (TTL 1h) to prevent duplicate publish.
        exchange_name: Override exchange. Defaults to the domain part of event_name.

    Returns:
        True if published, False if skipped due to deduplication.
    """
    if dedupe_key:
        redis = _get_redis()
        # SETNX — only set if not exists. Returns True if key was set (first time).
        key = f"evt:dedupe:{hashlib.sha256(dedupe_key.encode()).hexdigest()}"
        was_set: bool = await redis.set(key, "1", ex=3600, nx=True)  # type: ignore[assignment]
        if not was_set:
            logger.debug("Skipping duplicate event", extra={"event_name": event_name, "dedupe_key": dedupe_key})
            return False

    channel = await _get_channel()

    # Derive exchange name from domain prefix (e.g. "auth.user_signed_up" → "auth")
    domain = exchange_name or event_name.split(".")[0]

    exchange = await channel.declare_exchange(
        domain,
        aio_pika.ExchangeType.TOPIC,
        durable=True,
    )

    message_body = json.dumps(
        {"event": event_name, "data": payload},
        default=str,
    ).encode()

    await exchange.publish(
        aio_pika.Message(
            body=message_body,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key=event_name,
    )

    logger.info("Event published", extra={"event_name": event_name})
    return True


# ---------------------------------------------------------------------------
# Outbox helper — write to DB; relay worker handles actual publish
# ---------------------------------------------------------------------------


async def enqueue_outbox(
    session: Any,  # AsyncSession; avoid import cycle
    event_name: str,
    payload: dict[str, Any],
    *,
    dedupe_key: str | None = None,
) -> EventOutbox:
    """
    Write an event to the outbox table inside the current transaction.
    A relay worker will drain the outbox and publish to RabbitMQ.
    """
    entry = EventOutbox(
        event_name=event_name,
        payload=json.dumps(payload, default=str),
        dedupe_key=dedupe_key,
    )
    session.add(entry)
    await session.flush()
    return entry
