"""
matching-svc — RabbitMQ event consumer.

Handles:
  profile.updated → on-demand rerank if embedding changed
  profile.badge_granted → on-demand rerank
"""

from __future__ import annotations

import asyncio
import json
import logging

import aio_pika

from app.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()


async def _handle_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process():
        try:
            event = json.loads(message.body)
            event_type = event.get("type", "")
            payload = event.get("payload", {})

            if event_type in ("profile.updated", "profile.badge_granted"):
                profile_id = payload.get("profile_id", "")
                user_id = payload.get("user_id", "")
                if profile_id:
                    from app.workers.tasks import rerank_profile
                    rerank_profile.apply_async(args=[profile_id, user_id], countdown=5)
                    logger.info("Enqueued on-demand rerank for profile %s", profile_id)

        except Exception as exc:
            logger.exception("Event processing error: %s", exc)


async def start_consumer(rabbitmq_url: str) -> None:
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
                    "matching-svc.events", durable=True
                )
                for rk in ["profile.updated", "profile.badge_granted"]:
                    await queue.bind(exchange, routing_key=rk)

                await queue.consume(_handle_message)
                logger.info("matching-svc event consumer running")
                await asyncio.Future()
        except Exception as exc:
            logger.error("RabbitMQ connection error, retrying in 5s: %s", exc)
            await asyncio.sleep(5)
