"""
Celery tasks for Recall.ai bot dispatch.

MEET-TASK-1: dispatch_recall_bot(meeting_id)
MEET-TASK-3: send_consent_nudge(meeting_id)
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.bot_tasks.dispatch_recall_bot",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def dispatch_recall_bot(self, meeting_id: str) -> None:
    """
    Dispatch a Recall.ai bot to the meeting's Google Meet URL.

    Scheduled to run at Meeting.scheduled_at.
    On failure: marks bot_status='failed' and emits notification event.
    """
    asyncio.run(_dispatch_recall_bot_async(uuid.UUID(meeting_id)))


async def _dispatch_recall_bot_async(meeting_id: uuid.UUID) -> None:
    from sqlalchemy import select

    from app.config import get_settings
    from app.db import AsyncSessionLocal
    from app.models import Meeting
    from app.services.recall_client import RecallCircuitOpen, RecallClient
    from app.workers.events import emit_event

    settings = get_settings()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
        meeting = result.scalar_one_or_none()

        if not meeting:
            logger.error("dispatch_recall_bot: meeting %s not found", meeting_id)
            return

        if meeting.bot_status not in ("requested",):
            logger.info(
                "dispatch_recall_bot: meeting %s bot_status=%s — skipping",
                meeting_id, meeting.bot_status,
            )
            return

        recall = RecallClient(
            api_key=settings.recall_api_key,
            base_url=settings.recall_api_base_url,
            bot_name=settings.bot_name,
        )

        try:
            bot_id = await recall.create_bot(
                meeting_url=meeting.join_url,
                webhook_url=settings.recall_webhook_url,
            )
            meeting.recall_bot_id = bot_id
            meeting.bot_status = "joining"
            await db.commit()
            logger.info("Recall bot %s joining meeting %s", bot_id, meeting_id)

        except (RecallCircuitOpen, RuntimeError, Exception) as exc:
            logger.error("Recall bot dispatch failed for meeting %s: %s", meeting_id, exc)
            meeting.bot_status = "failed"
            await db.commit()

            await emit_event(
                "meeting.bot_failed",
                {
                    "meeting_id": str(meeting_id),
                    "collab_id": str(meeting.collab_id),
                    "reason": str(exc),
                },
            )


@celery_app.task(
    name="app.workers.bot_tasks.send_consent_nudge",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def send_consent_nudge(self, meeting_id: str) -> None:
    """
    30 minutes before scheduled_at: nudge non-consenting participant.
    Only fires if bot_enabled=True and not both_consented.
    """
    asyncio.run(_send_consent_nudge_async(uuid.UUID(meeting_id)))


async def _send_consent_nudge_async(meeting_id: uuid.UUID) -> None:
    from sqlalchemy import select

    from app.db import AsyncSessionLocal
    from app.models import Meeting, MeetingBotConsent
    from app.workers.events import emit_event

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
        meeting = result.scalar_one_or_none()

        if not meeting or not meeting.bot_enabled:
            return

        # Count active consents
        consents_result = await db.execute(
            select(MeetingBotConsent).where(
                MeetingBotConsent.meeting_id == meeting_id,
                MeetingBotConsent.revoked_at.is_(None),
            )
        )
        consents = consents_result.scalars().all()
        consent_profile_ids = {str(c.profile_id) for c in consents}

        if len(consents) >= 2:
            return  # Both consented — no nudge needed

        await emit_event(
            "meeting.bot_consent_pending",
            {
                "meeting_id": str(meeting_id),
                "collab_id": str(meeting.collab_id),
                "consented_profile_ids": list(consent_profile_ids),
            },
        )
        logger.info("Sent consent nudge for meeting %s", meeting_id)
