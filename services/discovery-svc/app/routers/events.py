"""
discovery-svc — RabbitMQ event consumer.

Listens for events that require cache invalidation:
  - profile.updated → invalidate feed cache
  - profile.blocked → invalidate feed cache for both users
  - billing.entitlement_changed → invalidate cap key
"""

from __future__ import annotations

import asyncio
import json
import logging

import aio_pika

from app.config import get_settings
from app.services.cache import invalidate_user_feed, invalidate_recs, get_redis

logger = logging.getLogger(__name__)
_settings = get_settings()


async def _handle_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process():
        try:
            event = json.loads(message.body)
            event_type = event.get("type", "")
            payload = event.get("payload", {})

            if event_type == "profile.updated":
                user_id = payload.get("user_id", "")
                if user_id:
                    await invalidate_user_feed(user_id)
                    if payload.get("embedding_changed"):
                        await invalidate_recs(user_id)

            elif event_type == "profile.blocked":
                blocker_id = payload.get("blocker_id", "")
                blocked_id = payload.get("blocked_id", "")
                for uid in [blocker_id, blocked_id]:
                    if uid:
                        await invalidate_user_feed(uid)

            elif event_type == "billing.entitlement_changed":
                user_id = payload.get("user_id", "")
                if user_id:
                    r = get_redis()
                    import re
                    # Delete all cap keys for this user (pattern delete via SCAN)
                    async for key in r.scan_iter(f"feed_cap:{user_id}:*"):
                        await r.delete(key)

            elif event_type == "hide_3mo.created":
                user_id = payload.get("user_id", "")
                if user_id:
                    await invalidate_user_feed(user_id)

            elif event_type == "match.score_recomputed":
                viewer_id = payload.get("viewer_user_id", "")
                if viewer_id:
                    await invalidate_user_feed(viewer_id)

        except Exception as exc:
            logger.exception("Event processing error: %s", exc)


async def start_consumer(rabbitmq_url: str) -> None:
    while True:
        try:
            connection = await aio_pika.connect_robust(rabbitmq_url)
            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=20)

                exchange = await channel.declare_exchange(
                    "colab.events", aio_pika.ExchangeType.TOPIC, durable=True
                )
                queue = await channel.declare_queue(
                    "discovery-svc.events", durable=True
                )
                routing_keys = [
                    "profile.updated",
                    "profile.blocked",
                    "billing.entitlement_changed",
                    "hide_3mo.created",
                    "match.score_recomputed",
                ]
                for rk in routing_keys:
                    await queue.bind(exchange, routing_key=rk)

                await queue.consume(_handle_message)
                logger.info("discovery-svc event consumer running")
                await asyncio.Future()  # run forever
        except Exception as exc:
            logger.error("RabbitMQ connection error, retrying in 5s: %s", exc)
            await asyncio.sleep(5)
