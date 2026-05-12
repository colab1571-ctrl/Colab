"""
invite-svc — RabbitMQ event consumer.

Consumes:
  entitlement.changed — invalidate Redis entitlement cache for user
"""

from __future__ import annotations

import asyncio
import json
import logging

import aio_pika

from app.config import get_settings
from app.services.quota import invalidate_entitlement_cache

logger = logging.getLogger(__name__)


async def _handle_message(message: aio_pika.IncomingMessage, redis) -> None:
    async with message.process():
        try:
            event = json.loads(message.body)
            event_type = event.get("event") or event.get("type", "")
            payload = event.get("payload", event)

            if event_type == "entitlement.changed":
                user_id_raw = payload.get("user_id")
                if user_id_raw:
                    import uuid
                    user_id = uuid.UUID(str(user_id_raw))
                    await invalidate_entitlement_cache(redis, user_id)
                    logger.info("Invalidated entitlement cache for user %s", user_id)

        except Exception as exc:
            logger.exception("Event processing error: %s", exc)


async def start_consumer(rabbitmq_url: str, redis) -> None:
    """Start RabbitMQ consumer for invite-svc relevant events."""
    while True:
        try:
            connection = await aio_pika.connect_robust(rabbitmq_url)
            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=10)

                exchange = await channel.declare_exchange(
                    "colab.events", aio_pika.ExchangeType.TOPIC, durable=True
                )
                queue = await channel.declare_queue(
                    "invite-svc.events", durable=True
                )

                routing_keys = [
                    "entitlement.changed",
                ]
                for rk in routing_keys:
                    await queue.bind(exchange, routing_key=rk)

                async def _handler(msg: aio_pika.IncomingMessage) -> None:
                    await _handle_message(msg, redis)

                await queue.consume(_handler)
                logger.info("invite-svc event consumer running")
                await asyncio.Future()  # run forever

        except Exception as exc:
            logger.error("RabbitMQ connection error, retrying in 5s: %s", exc)
            await asyncio.sleep(5)
