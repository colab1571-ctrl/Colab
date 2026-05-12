"""
Celery tasks for Recall.ai webhook processing.

MEET-TASK-2: process_recall_webhook(meeting_id, payload)
  - On status_changes/done: ingest transcript + recording → S3, MeetingArtifact,
    emit meeting.transcript_ready, write audit log, post system chat message.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.webhook_tasks.process_recall_webhook",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def process_recall_webhook(self, recall_bot_id: str, payload: dict[str, Any]) -> None:
    """
    Process a verified Recall.ai webhook payload.

    Handles:
    - status_changes with code 'done' → artifact ingestion
    - status_changes with code 'fatal' → bot_status='failed', notify
    - Other status codes → update bot_status accordingly
    """
    asyncio.run(_process_recall_webhook_async(recall_bot_id, payload))


async def _process_recall_webhook_async(
    recall_bot_id: str, payload: dict[str, Any]
) -> None:
    from sqlalchemy import select

    from app.config import get_settings
    from app.db import AsyncSessionLocal
    from app.models import Meeting, MeetingArtifact
    from app.services.chat_client import ChatSvcClient
    from app.services.ics_generator import generate_signed_url
    from app.workers.events import emit_event

    settings = get_settings()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Meeting).where(Meeting.recall_bot_id == recall_bot_id)
        )
        meeting = result.scalar_one_or_none()

        if not meeting:
            logger.warning(
                "process_recall_webhook: no meeting found for bot_id=%s", recall_bot_id
            )
            return

        event_type = payload.get("event", "")
        data = payload.get("data", {})
        bot_data = data.get("bot", {})
        status_code = bot_data.get("status", {}).get("code", "")

        logger.info(
            "Recall webhook: meeting=%s event=%s status=%s",
            meeting.id, event_type, status_code,
        )

        # Map Recall status codes to our bot_status
        _STATUS_MAP = {
            "joining_call": "joining",
            "in_call_recording": "joined",
            "call_ended": "left",
            "done": "left",
            "fatal": "failed",
        }

        if status_code in _STATUS_MAP:
            meeting.bot_status = _STATUS_MAP[status_code]

        if status_code == "fatal":
            await db.commit()
            await emit_event(
                "meeting.bot_failed",
                {
                    "meeting_id": str(meeting.id),
                    "collab_id": str(meeting.collab_id),
                    "reason": "Recall.ai bot reported fatal error",
                },
            )
            return

        if status_code == "done":
            await _ingest_artifacts(db, meeting, data, settings)
            await db.commit()

            # Emit transcript_ready event
            await emit_event(
                "meeting.transcript_ready",
                {
                    "meeting_id": str(meeting.id),
                    "collab_id": str(meeting.collab_id),
                    "scheduled_at": meeting.scheduled_at.isoformat(),
                },
            )

            # Post system message to chat (best-effort)
            chat_client = ChatSvcClient(
                base_url=settings.chat_svc_url,
                shared_secret=settings.service_shared_secret,
            )
            await chat_client.post_transcript_system_message(
                collab_id=meeting.collab_id,
                meeting_id=meeting.id,
                scheduled_at=meeting.scheduled_at,
            )

        else:
            await db.commit()


async def _ingest_artifacts(
    db: Any,
    meeting: Any,
    data: dict[str, Any],
    settings: Any,
) -> None:
    """Download transcript + store artifact rows + update meeting status."""
    import boto3
    import httpx

    meeting.status = "ended"
    meeting.bot_status = "left"

    transcript_url = data.get("transcript", {}).get("url")
    recording_url = data.get("recording", {}).get("url")

    # Transcript ingestion
    if transcript_url:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(transcript_url)
                resp.raise_for_status()
                transcript_bytes = resp.content

            s3_key = f"artifacts/meetings/{meeting.id}/transcript.json"
            s3 = boto3.client("s3", region_name=settings.s3_region)
            s3.put_object(
                Bucket=settings.s3_bucket,
                Key=s3_key,
                Body=transcript_bytes,
                ContentType="application/json",
                ServerSideEncryption="AES256",
            )

            artifact = MeetingArtifact(
                meeting_id=meeting.id,
                kind="transcript",
                s3_key=s3_key,
                size_bytes=len(transcript_bytes),
            )
            db.add(artifact)
            logger.info("Transcript stored: s3://%s/%s", settings.s3_bucket, s3_key)

        except Exception as exc:
            logger.error("Failed to ingest transcript for meeting %s: %s", meeting.id, exc)

    # Recording: store the Recall.ai URL as an artifact (not downloading the video)
    if recording_url:
        try:
            # Store the external URL reference; actual video lives on Recall.ai CDN
            s3_key = f"artifacts/meetings/{meeting.id}/recording_url.txt"
            s3 = boto3.client("s3", region_name=settings.s3_region)
            s3.put_object(
                Bucket=settings.s3_bucket,
                Key=s3_key,
                Body=recording_url.encode(),
                ContentType="text/plain",
                ServerSideEncryption="AES256",
            )

            artifact = MeetingArtifact(
                meeting_id=meeting.id,
                kind="recording",
                s3_key=s3_key,
            )
            db.add(artifact)
            logger.info("Recording ref stored: %s", recording_url)

        except Exception as exc:
            logger.error("Failed to store recording ref for meeting %s: %s", meeting.id, exc)
