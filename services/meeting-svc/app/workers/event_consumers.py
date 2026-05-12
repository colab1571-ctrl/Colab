"""
RabbitMQ event consumers for meeting-svc.

Consumed events:
- meeting.transcript_ready → post system message to chat-svc
  (also handled directly in webhook_tasks; this is the queue-based fallback)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

import aio_pika

from app.config import get_settings
from app.services.chat_client import ChatSvcClient

logger = logging.getLogger(__name__)
settings = get_settings()


async def start_consumers() -> None:
    """Start all RabbitMQ consumers. Called from FastAPI lifespan."""
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)

    exchange = await channel.declare_exchange(
        "colab.events", aio_pika.ExchangeType.TOPIC, durable=True
    )

    queue_map = {
        "meeting-svc.meeting.transcript_ready": "meeting.transcript_ready",
    }

    handler_map = {
        "meeting.transcript_ready": _handle_transcript_ready,
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

            return on_message

        consumer = await make_consumer(routing_key)
        await queue.consume(consumer)
        logger.info("Consumer started for %s", routing_key)

    logger.info("All meeting-svc consumers running")
    # Keep running
    try:
        import asyncio
        await asyncio.Future()
    except asyncio.CancelledError:
        await connection.close()


async def _handle_transcript_ready(payload: dict) -> None:
    """
    meeting.transcript_ready consumed from queue.

    Posts a system transcript message to chat-svc if not already done.
    This is a safety net; the Celery webhook task also posts directly.
    """
    meeting_id_str = payload.get("meeting_id")
    collab_id_str = payload.get("collab_id")
    scheduled_at_str = payload.get("scheduled_at")

    if not meeting_id_str or not collab_id_str:
        logger.warning("transcript_ready: missing meeting_id or collab_id in payload")
        return

    meeting_id = uuid.UUID(meeting_id_str)
    collab_id = uuid.UUID(collab_id_str)
    scheduled_at = (
        datetime.fromisoformat(scheduled_at_str) if scheduled_at_str else None
    )

    if scheduled_at is None:
        # Fetch from DB
        from sqlalchemy import select

        from app.db import AsyncSessionLocal
        from app.models import Meeting

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
            meeting = result.scalar_one_or_none()
            if meeting:
                scheduled_at = meeting.scheduled_at

    if scheduled_at is None:
        logger.warning("transcript_ready: could not determine scheduled_at for meeting %s", meeting_id)
        return

    chat_client = ChatSvcClient(
        base_url=settings.chat_svc_url,
        shared_secret=settings.service_shared_secret,
    )
    await chat_client.post_transcript_system_message(
        collab_id=collab_id,
        meeting_id=meeting_id,
        scheduled_at=scheduled_at,
    )
    logger.info("Transcript system message posted for meeting %s", meeting_id)
