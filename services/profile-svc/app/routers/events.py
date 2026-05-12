"""
profile-svc — RabbitMQ event consumer for:
  user.created → create profile shell (idempotent)
  user.email_verified → advance badge to email_verified
  identity.inquiry_started → advance to identity_pending
  identity.verified → advance to identity_approved + fire AI review
  identity.declined → revert to email_verified
  identity.needs_review → stay pending + mod queue
  moderation.cleared / moderation.upheld / moderation.appeal_upheld → badge FSM

This module starts an asyncio aio-pika consumer. Called on startup.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import aio_pika

logger = logging.getLogger(__name__)


async def _handle_event(event_name: str, payload: dict[str, Any]) -> None:
    """Dispatch incoming event to badge FSM."""
    from app.db import async_session_factory
    from app.models import Profile
    from app.services.badge_fsm import BadgeEvent, BadgeState, transition
    from sqlalchemy import select

    user_id_str = payload.get("user_id") or payload.get("subject_id")
    if not user_id_str:
        logger.warning("Event %s missing user_id/subject_id", event_name)
        return

    # Map event name → BadgeEvent
    event_map = {
        "user.created": None,  # special: create shell
        "user.email_verified": BadgeEvent.user_email_verified,
        "identity.inquiry_started": BadgeEvent.identity_inquiry_started,
        "identity.verified": BadgeEvent.identity_verified,
        "identity.declined": BadgeEvent.identity_declined,
        "identity.needs_review": BadgeEvent.identity_needs_review,
        "moderation.cleared": BadgeEvent.moderation_cleared,
        "moderation.upheld": BadgeEvent.moderation_upheld,
        "moderation.appeal_upheld": BadgeEvent.moderation_appeal_upheld,
        "user.deleted": BadgeEvent.user_deleted,
    }

    if event_name not in event_map:
        return

    badge_event = event_map[event_name]
    user_id = uuid.UUID(user_id_str)

    async with async_session_factory() as session:
        if event_name == "user.created":
            # Idempotent profile shell creation
            existing = await session.execute(
                select(Profile).where(Profile.user_id == user_id)
            )
            if not existing.scalar_one_or_none():
                profile = Profile(user_id=user_id, badge_state="unverified")
                session.add(profile)
                await session.commit()
                logger.info("Created profile shell for user %s", user_id)
            return

        # For all other events: find profile and advance FSM
        result = await session.execute(select(Profile).where(Profile.user_id == user_id))
        profile = result.scalar_one_or_none()

        if not profile:
            # For moderation events, profile may be addressed by profile_id
            profile_id_str = payload.get("profile_id")
            if profile_id_str:
                profile = await session.get(Profile, uuid.UUID(profile_id_str))
        if not profile:
            logger.warning("No profile for user %s on event %s", user_id, event_name)
            return

        try:
            fsm_result = transition(profile.badge_state, badge_event)
            profile.badge_state = fsm_result.new_state.value
            if fsm_result.badge_held_reason:
                profile.badge_held_reason = fsm_result.badge_held_reason
            if profile.badge_state == BadgeState.badge_granted.value:
                profile.badge_granted_at = datetime.now(tz=timezone.utc)
                profile.badge_held_reason = None

            await session.commit()
            logger.info("Badge FSM: %s + %s → %s (user=%s)", badge_event, event_name, profile.badge_state, user_id)

            # Side effects
            for effect in fsm_result.side_effects:
                if effect == "ai.review.fire":
                    from app.workers.ai_review_tasks import orchestrate_profile_review
                    orchestrate_profile_review.delay(str(profile.id), event_name)

        except Exception as exc:
            logger.info("No FSM transition for state=%s event=%s: %s", profile.badge_state, event_name, exc)


async def start_consumer(rabbitmq_url: str) -> None:
    """Start consuming events from RabbitMQ. Runs as background task on app startup."""
    try:
        connection = await aio_pika.connect_robust(rabbitmq_url)
        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=10)

            exchange = await channel.declare_exchange("colab.events", aio_pika.ExchangeType.TOPIC, durable=True)
            queue = await channel.declare_queue("profile-svc.events", durable=True)

            # Bind to relevant events
            routing_keys = [
                "user.created",
                "user.email_verified",
                "user.deleted",
                "identity.inquiry_started",
                "identity.verified",
                "identity.declined",
                "identity.needs_review",
                "moderation.cleared",
                "moderation.upheld",
                "moderation.appeal_upheld",
            ]
            for key in routing_keys:
                await queue.bind(exchange, routing_key=key)

            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        try:
                            body = json.loads(message.body.decode())
                            event_name = message.routing_key or body.get("event", "")
                            await _handle_event(event_name, body)
                        except Exception:
                            logger.exception("Error processing event %s", message.routing_key)
    except Exception:
        logger.exception("RabbitMQ consumer error; will retry on next startup")
