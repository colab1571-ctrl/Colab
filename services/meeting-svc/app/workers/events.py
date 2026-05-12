"""
RabbitMQ event emission helpers for meeting-svc.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aio_pika

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def emit_event(routing_key: str, payload: dict[str, Any]) -> None:
    """
    Publish a JSON event to RabbitMQ topic exchange `colab.events`.
    Best-effort: logs warning on failure but does not raise.
    """
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        async with connection:
            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                "colab.events", aio_pika.ExchangeType.TOPIC, durable=True
            )
            message = aio_pika.Message(
                body=json.dumps(payload).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            await exchange.publish(message, routing_key=routing_key)
            logger.debug("Emitted event %s: %s", routing_key, payload)
    except Exception as exc:
        logger.warning("Failed to emit event %s: %s", routing_key, exc)


def emit_event_sync(routing_key: str, payload: dict[str, Any]) -> None:
    """Synchronous wrapper for use from Celery tasks."""
    asyncio.run(emit_event(routing_key, payload))
