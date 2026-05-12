"""
RabbitMQ consumer runner for notification-svc.

Binds to the colab.events topic exchange and routes incoming events
to Celery tasks for async processing.

Routing key → handler mapping per plan §8.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from colab_common.settings import get_settings
from colab_common.db import session_scope

from ..schemas import (
    AIMockupGeneratedEvent,
    ChatFileSentEvent,
    ChatMessageSentEvent,
    CollabNudgeDueEvent,
    CollabStatusUpdatedEvent,
    InviteAcceptedEvent,
    InviteSentEvent,
    MarketingBroadcastEvent,
    MatchCreatedEvent,
    SupportTicketRepliedEvent,
    UserCreatedEvent,
)
from ..preferences import seed_preferences
from ..workers.tasks import (
    task_ai_mockup_ready,
    task_chat_message,
    task_collab_nudge,
    task_collab_status_change,
    task_file_shared,
    task_marketing,
    task_new_match,
    task_new_request,
    task_request_accepted,
    task_support_reply,
)

logger = logging.getLogger(__name__)

QUEUE_NAME = "notification-svc.inbound"
EXCHANGE_NAME = "colab.events"

ROUTING_KEYS = [
    "match.created",
    "invite.sent",
    "invite.accepted",
    "chat.message.sent",
    "chat.file.sent",
    "ai.mockup_generated",
    "collab.nudge_due",
    "collab.status_updated",
    "support.ticket_replied",
    "marketing.broadcast",
    "user.created",
]


async def handle_message(message: AbstractIncomingMessage) -> None:
    """Route an incoming AMQP message to the correct handler."""
    async with message.process(requeue=True):
        try:
            body = json.loads(message.body)
            routing_key = message.routing_key or ""
            data = body.get("data", body)
            logger.debug("Received event", extra={"routing_key": routing_key})
            await _route(routing_key, data)
        except Exception as exc:
            logger.error("Failed to process message: %s", exc, exc_info=True)
            raise  # requeue on failure


async def _route(routing_key: str, data: dict[str, Any]) -> None:
    if routing_key == "match.created":
        evt = MatchCreatedEvent(**data)
        # Both users get a notification
        task_new_match.delay(
            user_id=str(evt.user_id_a),
            other_user_display_name=evt.user_b_display_name,
            collab_id=str(evt.collab_id),
            match_id=str(evt.match_id),
        )
        task_new_match.delay(
            user_id=str(evt.user_id_b),
            other_user_display_name=evt.user_a_display_name,
            collab_id=str(evt.collab_id),
            match_id=str(evt.match_id),
        )

    elif routing_key == "invite.sent":
        evt = InviteSentEvent(**data)
        task_new_request.delay(
            user_id=str(evt.recipient_user_id),
            sender_display_name=evt.sender_display_name,
            synopsis=evt.synopsis,
            invite_id=str(evt.invite_id),
        )

    elif routing_key == "invite.accepted":
        evt = InviteAcceptedEvent(**data)
        task_request_accepted.delay(
            user_id=str(evt.sender_user_id),
            acceptor_display_name=evt.acceptor_display_name,
            collab_id=str(evt.collab_id),
            invite_id=str(evt.invite_id),
        )

    elif routing_key == "chat.message.sent":
        evt = ChatMessageSentEvent(**data)
        task_chat_message.delay(
            user_id=str(evt.recipient_user_id),
            sender_display_name=evt.sender_display_name,
            message_preview=evt.message_preview,
            message_type=evt.message_type,
            collab_id=str(evt.collab_id),
            message_id=str(evt.message_id),
        )

    elif routing_key == "chat.file.sent":
        evt = ChatFileSentEvent(**data)
        task_file_shared.delay(
            user_id=str(evt.recipient_user_id),
            sender_display_name=evt.sender_display_name,
            file_name=evt.file_name,
            file_type=evt.file_type,
            collab_id=str(evt.collab_id),
        )

    elif routing_key == "ai.mockup_generated":
        evt = AIMockupGeneratedEvent(**data)
        task_ai_mockup_ready.delay(
            user_id=str(evt.user_id_a),
            collab_id=str(evt.collab_id),
            mockup_id=str(evt.mockup_id),
            expires_at=evt.expires_at.isoformat(),
            mockup_type=evt.mockup_type,
        )
        task_ai_mockup_ready.delay(
            user_id=str(evt.user_id_b),
            collab_id=str(evt.collab_id),
            mockup_id=str(evt.mockup_id),
            expires_at=evt.expires_at.isoformat(),
            mockup_type=evt.mockup_type,
        )

    elif routing_key == "collab.nudge_due":
        evt = CollabNudgeDueEvent(**data)
        task_collab_nudge.delay(
            user_id=str(evt.user_id_a),
            collab_id=str(evt.collab_id),
            other_user_display_name=evt.user_b_display_name,
            inactive_days=evt.inactive_days,
            nudge_cycle_date=evt.nudge_cycle_date,
            auto_archive_at=evt.auto_archive_at.isoformat(),
        )
        task_collab_nudge.delay(
            user_id=str(evt.user_id_b),
            collab_id=str(evt.collab_id),
            other_user_display_name=evt.user_a_display_name,
            inactive_days=evt.inactive_days,
            nudge_cycle_date=evt.nudge_cycle_date,
            auto_archive_at=evt.auto_archive_at.isoformat(),
        )

    elif routing_key == "collab.status_updated":
        evt = CollabStatusUpdatedEvent(**data)
        task_collab_status_change.delay(
            user_id=str(evt.other_user_id),
            collab_id=str(evt.collab_id),
            other_user_display_name=evt.other_user_display_name,
            new_status=evt.new_status,
        )

    elif routing_key == "support.ticket_replied":
        evt = SupportTicketRepliedEvent(**data)
        task_support_reply.delay(
            user_id=str(evt.user_id),
            ticket_id=str(evt.ticket_id),
            ticket_subject=evt.ticket_subject,
            reply_preview=evt.reply_preview,
            replied_by=evt.replied_by,
        )

    elif routing_key == "marketing.broadcast":
        evt = MarketingBroadcastEvent(**data)
        # Fan-out to users is handled here — in production, iterate user IDs
        # from a paginated list filtered by segment. Stub task for now.
        logger.info("Marketing broadcast received: campaign=%s segment=%s", evt.campaign_id, evt.segment)

    elif routing_key == "user.created":
        evt = UserCreatedEvent(**data)
        async with session_scope() as session:
            await seed_preferences(session, str(evt.user_id))

    else:
        logger.warning("Unknown routing key: %s", routing_key)


async def start_consumer() -> None:
    """Start the AMQP consumer. Runs until cancelled."""
    settings = get_settings()
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)

    exchange = await channel.declare_exchange(
        EXCHANGE_NAME,
        aio_pika.ExchangeType.TOPIC,
        durable=True,
    )

    queue = await channel.declare_queue(QUEUE_NAME, durable=True)

    for rk in ROUTING_KEYS:
        await queue.bind(exchange, routing_key=rk)

    logger.info("notification-svc consumer ready, bound to %d routing keys", len(ROUTING_KEYS))
    await queue.consume(handle_message)

    try:
        await asyncio.Future()  # run forever
    finally:
        await connection.close()
