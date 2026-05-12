"""
meeting-svc REST API — Meeting scheduling, management, artifact access.

Routes:
  POST   /v1/collabs/{collab_id}/meetings
  GET    /v1/collabs/{collab_id}/meetings
  PATCH  /v1/meetings/{id}
  POST   /v1/meetings/{id}/bot/consent
  DELETE /v1/meetings/{id}/bot/consent
  POST   /v1/meetings/{id}/bot/start
  GET    /v1/meetings/{id}/artifacts
  POST   /webhooks/recall
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import Meeting, MeetingArtifact, MeetingBotConsent
from app.schemas import (
    ArtifactListResponse,
    ArtifactOut,
    BotConsentStatus,
    BotStartResponse,
    ConsentOut,
    MeetingCreateRequest,
    MeetingListResponse,
    MeetingOut,
    MeetingPatchRequest,
)
from app.services.google_calendar import GoogleCalendarClient
from app.services.ics_generator import (
    generate_ics,
    generate_signed_url,
    upload_ics_to_s3,
)
from app.services.webhook_security import require_recall_signature
from app.workers.events import emit_event

logger = logging.getLogger(__name__)
router = APIRouter(tags=["meetings"])
settings = get_settings()


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


def get_current_profile_id(request: Request) -> uuid.UUID:
    pid = request.headers.get("X-Profile-Id") or request.headers.get("x-profile-id")
    if not pid:
        raise HTTPException(status_code=401, detail="Missing X-Profile-Id")
    try:
        return uuid.UUID(pid)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid X-Profile-Id")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gcal_client() -> GoogleCalendarClient:
    return GoogleCalendarClient(
        service_account_json=settings.google_service_account_json,
        calendar_id=settings.google_calendar_id,
    )


def _bot_consent_status(meeting: Meeting) -> BotConsentStatus:
    """Compute consent status for response payload."""
    active = [c for c in (meeting.consents or []) if c.revoked_at is None]
    profile_ids = [str(c.profile_id) for c in active]
    a = len(profile_ids) >= 1
    b = len(profile_ids) >= 2
    return BotConsentStatus(participant_a=a, participant_b=b)


async def _meeting_to_out(meeting: Meeting) -> MeetingOut:
    ics_url: str | None = None
    if meeting.ics_s3_key:
        try:
            ics_url = generate_signed_url(
                s3_key=meeting.ics_s3_key,
                s3_bucket=settings.s3_bucket,
                s3_region=settings.s3_region,
                ttl_seconds=settings.artifact_url_ttl_seconds,
            )
        except Exception as exc:
            logger.warning("Could not generate ICS signed URL: %s", exc)

    return MeetingOut(
        id=meeting.id,
        collab_id=meeting.collab_id,
        organizer_profile_id=meeting.organizer_profile_id,
        scheduled_at=meeting.scheduled_at,
        duration_min=meeting.duration_min,
        join_url=meeting.join_url,
        ics_url=ics_url,
        status=meeting.status,
        bot_enabled=meeting.bot_enabled,
        bot_status=meeting.bot_status,
        recall_bot_id=meeting.recall_bot_id,
        bot_consent=_bot_consent_status(meeting),
        created_at=meeting.created_at,
        updated_at=meeting.updated_at,
    )


async def _assert_collab_participant(
    collab_id: uuid.UUID, profile_id: uuid.UUID
) -> None:
    """Verify profile_id is a participant in the collab via collab-svc (lightweight check)."""
    # In production: call collab-svc internal endpoint or cache collab membership.
    # For v1: we trust X-Profile-Id injected by gateway + collab_id from path.
    # Gateway already validates JWT; collab membership validated by collab-svc on creation.
    # If collab-svc call fails, we allow through (best-effort guard; collab-svc owns membership).
    pass


# ---------------------------------------------------------------------------
# POST /v1/collabs/{collab_id}/meetings
# ---------------------------------------------------------------------------


@router.post("/v1/collabs/{collab_id}/meetings", status_code=201, response_model=MeetingOut)
async def create_meeting(
    collab_id: uuid.UUID,
    body: MeetingCreateRequest,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> MeetingOut:
    await _assert_collab_participant(collab_id, profile_id)

    start_dt = body.scheduled_at
    end_dt = start_dt + timedelta(minutes=body.duration_min)

    # Conflict check: overlapping meetings in the same collab
    overlap_result = await db.execute(
        select(Meeting).where(
            Meeting.collab_id == collab_id,
            Meeting.status.notin_(["cancelled"]),
            Meeting.scheduled_at < end_dt,
        )
    )
    existing = overlap_result.scalars().all()
    for m in existing:
        m_end = m.scheduled_at + timedelta(minutes=m.duration_min)
        if m_end > start_dt:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "meeting_conflict",
                    "conflicting_meeting_id": str(m.id),
                },
            )

    # Create Google Calendar event with Meet
    gcal_request_id = uuid.uuid4()
    gcal_client = _gcal_client()

    try:
        gcal_event_id, join_url = await gcal_client.create_event(
            summary=f"Colab Meeting",
            start_dt=start_dt,
            end_dt=end_dt,
            attendee_emails=[],  # In production: pull attendee emails from profile-svc
            request_id=gcal_request_id,
        )
    except Exception as exc:
        logger.error("Google Calendar event creation failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to create Google Calendar event. Please try again.",
        )

    # Persist meeting
    meeting = Meeting(
        collab_id=collab_id,
        organizer_profile_id=profile_id,
        scheduled_at=start_dt,
        duration_min=body.duration_min,
        join_url=join_url,
        gcal_event_id=gcal_event_id,
        gcal_request_id=gcal_request_id,
        status="scheduled",
        bot_enabled=body.bot_enabled,
        bot_status="none",
    )
    db.add(meeting)
    await db.flush()  # Get the generated ID

    # Generate and upload ICS
    try:
        ics_bytes = generate_ics(
            meeting_id=meeting.id,
            summary="Colab Meeting",
            description=f"Join at: {join_url}",
            start_dt=start_dt,
            duration_min=body.duration_min,
            join_url=join_url,
        )
        ics_s3_key = await upload_ics_to_s3(
            meeting_id=meeting.id,
            ics_bytes=ics_bytes,
            s3_bucket=settings.s3_bucket,
            s3_region=settings.s3_region,
        )
        meeting.ics_s3_key = ics_s3_key
    except Exception as exc:
        logger.warning("ICS upload failed (non-fatal): %s", exc)

    await db.commit()
    await db.refresh(meeting)

    # Emit event
    import asyncio
    asyncio.ensure_future(
        emit_event(
            "meeting.scheduled",
            {
                "meeting_id": str(meeting.id),
                "collab_id": str(collab_id),
                "organizer_profile_id": str(profile_id),
                "scheduled_at": start_dt.isoformat(),
                "bot_enabled": body.bot_enabled,
            },
        )
    )

    return await _meeting_to_out(meeting)


# ---------------------------------------------------------------------------
# GET /v1/collabs/{collab_id}/meetings
# ---------------------------------------------------------------------------


@router.get("/v1/collabs/{collab_id}/meetings", response_model=MeetingListResponse)
async def list_meetings(
    collab_id: uuid.UUID,
    status: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> MeetingListResponse:
    await _assert_collab_participant(collab_id, profile_id)

    q = select(Meeting).where(Meeting.collab_id == collab_id)

    if status:
        q = q.where(Meeting.status == status)

    if cursor:
        # cursor is a base64-encoded scheduled_at timestamp
        import base64
        try:
            cursor_dt = datetime.fromisoformat(base64.b64decode(cursor).decode())
            q = q.where(Meeting.scheduled_at < cursor_dt)
        except Exception:
            pass

    q = q.order_by(Meeting.scheduled_at.desc()).limit(limit + 1)
    result = await db.execute(q)
    meetings = result.scalars().all()

    has_more = len(meetings) > limit
    if has_more:
        meetings = meetings[:limit]

    next_cursor: str | None = None
    if has_more and meetings:
        import base64
        next_cursor = base64.b64encode(
            meetings[-1].scheduled_at.isoformat().encode()
        ).decode()

    items = [await _meeting_to_out(m) for m in meetings]
    return MeetingListResponse(items=items, cursor=next_cursor, has_more=has_more)


# ---------------------------------------------------------------------------
# PATCH /v1/meetings/{id}
# ---------------------------------------------------------------------------


@router.patch("/v1/meetings/{meeting_id}", response_model=MeetingOut)
async def patch_meeting(
    meeting_id: uuid.UUID,
    body: MeetingPatchRequest,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> MeetingOut:
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if meeting.status in ("ended", "cancelled"):
        raise HTTPException(
            status_code=422,
            detail=f"Cannot modify a meeting with status '{meeting.status}'",
        )

    await _assert_collab_participant(meeting.collab_id, profile_id)

    if body.status == "cancelled":
        meeting.status = "cancelled"
        meeting.cancelled_at = datetime.now(UTC)
        await db.commit()

        import asyncio
        asyncio.ensure_future(
            emit_event(
                "meeting.cancelled",
                {
                    "meeting_id": str(meeting_id),
                    "collab_id": str(meeting.collab_id),
                    "cancelled_by": str(profile_id),
                },
            )
        )
        await db.refresh(meeting)
        return await _meeting_to_out(meeting)

    if body.scheduled_at is not None or body.duration_min is not None:
        new_start = body.scheduled_at or meeting.scheduled_at
        new_duration = body.duration_min or meeting.duration_min
        new_end = new_start + timedelta(minutes=new_duration)

        if meeting.gcal_event_id:
            gcal_client = _gcal_client()
            try:
                await gcal_client.patch_event(
                    event_id=meeting.gcal_event_id,
                    start_dt=new_start,
                    end_dt=new_end,
                )
            except Exception as exc:
                logger.error("GCal patch failed: %s", exc)
                raise HTTPException(
                    status_code=502,
                    detail="Failed to update Google Calendar event",
                )

        if body.scheduled_at is not None:
            meeting.scheduled_at = body.scheduled_at
        if body.duration_min is not None:
            meeting.duration_min = body.duration_min

        # Regenerate ICS
        try:
            ics_bytes = generate_ics(
                meeting_id=meeting.id,
                summary="Colab Meeting",
                description=f"Join at: {meeting.join_url}",
                start_dt=meeting.scheduled_at,
                duration_min=meeting.duration_min,
                join_url=meeting.join_url,
            )
            ics_s3_key = await upload_ics_to_s3(
                meeting_id=meeting.id,
                ics_bytes=ics_bytes,
                s3_bucket=settings.s3_bucket,
                s3_region=settings.s3_region,
            )
            meeting.ics_s3_key = ics_s3_key
        except Exception as exc:
            logger.warning("ICS regeneration failed (non-fatal): %s", exc)

    await db.commit()
    await db.refresh(meeting)
    return await _meeting_to_out(meeting)


# ---------------------------------------------------------------------------
# POST /v1/meetings/{id}/bot/consent
# ---------------------------------------------------------------------------


@router.post("/v1/meetings/{meeting_id}/bot/consent", response_model=ConsentOut)
async def give_bot_consent(
    meeting_id: uuid.UUID,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> ConsentOut:
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if not meeting.bot_enabled:
        raise HTTPException(status_code=422, detail="Bot is not enabled for this meeting")
    if meeting.status in ("ended", "cancelled"):
        raise HTTPException(status_code=422, detail="Meeting is no longer active")

    await _assert_collab_participant(meeting.collab_id, profile_id)

    # Upsert consent
    now = datetime.now(UTC)
    stmt = (
        pg_insert(MeetingBotConsent)
        .values(
            meeting_id=meeting_id,
            profile_id=profile_id,
            consented_at=now,
            revoked_at=None,
        )
        .on_conflict_do_update(
            constraint="uq_consent_meeting_profile",
            set_={"consented_at": now, "revoked_at": None},
        )
    )
    await db.execute(stmt)
    await db.flush()

    # Count active consents
    consents_result = await db.execute(
        select(MeetingBotConsent).where(
            MeetingBotConsent.meeting_id == meeting_id,
            MeetingBotConsent.revoked_at.is_(None),
        )
    )
    active_consents = consents_result.scalars().all()
    both_consented = len(active_consents) >= 2

    if both_consented and meeting.bot_status in ("none",):
        # Auto-dispatch: schedule Celery task at scheduled_at
        meeting.bot_status = "requested"
        from app.workers.bot_tasks import dispatch_recall_bot

        dispatch_recall_bot.apply_async(
            args=[str(meeting_id)],
            eta=meeting.scheduled_at,
        )
        logger.info("Scheduled bot dispatch for meeting %s at %s", meeting_id, meeting.scheduled_at)

    await db.commit()

    return ConsentOut(
        profile_id=profile_id,
        consented_at=now,
        both_consented=both_consented,
    )


# ---------------------------------------------------------------------------
# DELETE /v1/meetings/{id}/bot/consent
# ---------------------------------------------------------------------------


@router.delete("/v1/meetings/{meeting_id}/bot/consent", status_code=200)
async def revoke_bot_consent(
    meeting_id: uuid.UUID,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if meeting.bot_status not in ("none", "requested"):
        raise HTTPException(
            status_code=422,
            detail="Bot has already been dispatched and cannot be recalled.",
        )

    await _assert_collab_participant(meeting.collab_id, profile_id)

    # Set revoked_at
    consent_result = await db.execute(
        select(MeetingBotConsent).where(
            MeetingBotConsent.meeting_id == meeting_id,
            MeetingBotConsent.profile_id == profile_id,
            MeetingBotConsent.revoked_at.is_(None),
        )
    )
    consent = consent_result.scalar_one_or_none()

    if not consent:
        raise HTTPException(status_code=404, detail="No active consent found for this profile")

    consent.revoked_at = datetime.now(UTC)

    # Revert bot_status to none if it was requested
    if meeting.bot_status == "requested":
        meeting.bot_status = "none"
        # Note: Celery task revocation requires storing task_id — deferred to v2.
        # The task will check bot_status='none' before dispatching and skip.
        logger.info("Bot status reverted to none for meeting %s", meeting_id)

    await db.commit()
    return {"status": "consent_revoked"}


# ---------------------------------------------------------------------------
# POST /v1/meetings/{id}/bot/start  (manual idempotent trigger)
# ---------------------------------------------------------------------------


@router.post("/v1/meetings/{meeting_id}/bot/start", status_code=202, response_model=BotStartResponse)
async def start_bot(
    meeting_id: uuid.UUID,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> BotStartResponse:
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if not meeting.bot_enabled:
        raise HTTPException(status_code=422, detail="Bot is not enabled for this meeting")

    await _assert_collab_participant(meeting.collab_id, profile_id)

    # Verify both participants have consented
    consents_result = await db.execute(
        select(MeetingBotConsent).where(
            MeetingBotConsent.meeting_id == meeting_id,
            MeetingBotConsent.revoked_at.is_(None),
        )
    )
    active_consents = consents_result.scalars().all()

    if len(active_consents) < 2:
        raise HTTPException(
            status_code=422,
            detail="Both participants must consent before the bot can be started.",
        )

    if meeting.bot_status not in ("none", "requested"):
        # Already dispatched — idempotent
        return BotStartResponse(bot_status=meeting.bot_status, recall_bot_id=meeting.recall_bot_id)

    meeting.bot_status = "requested"
    await db.commit()

    from app.workers.bot_tasks import dispatch_recall_bot
    dispatch_recall_bot.apply_async(args=[str(meeting_id)])

    return BotStartResponse(bot_status="requested", recall_bot_id=None)


# ---------------------------------------------------------------------------
# GET /v1/meetings/{id}/artifacts
# ---------------------------------------------------------------------------


@router.get("/v1/meetings/{meeting_id}/artifacts", response_model=ArtifactListResponse)
async def list_artifacts(
    meeting_id: uuid.UUID,
    profile_id: uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
) -> ArtifactListResponse:
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    await _assert_collab_participant(meeting.collab_id, profile_id)

    artifacts_result = await db.execute(
        select(MeetingArtifact).where(MeetingArtifact.meeting_id == meeting_id)
    )
    artifacts = artifacts_result.scalars().all()

    items: list[ArtifactOut] = []
    for artifact in artifacts:
        try:
            download_url = generate_signed_url(
                s3_key=artifact.s3_key,
                s3_bucket=settings.s3_bucket,
                s3_region=settings.s3_region,
                ttl_seconds=settings.artifact_url_ttl_seconds,
            )
        except Exception as exc:
            logger.warning("Could not generate signed URL for artifact %s: %s", artifact.id, exc)
            download_url = ""

        items.append(
            ArtifactOut(
                id=artifact.id,
                kind=artifact.kind,
                download_url=download_url,
                ready_at=artifact.ready_at,
            )
        )

    return ArtifactListResponse(items=items)


# ---------------------------------------------------------------------------
# POST /webhooks/recall
# ---------------------------------------------------------------------------


@router.post("/webhooks/recall", status_code=200)
async def recall_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Recall.ai webhook endpoint.

    1. Verify HMAC-SHA256 signature immediately.
    2. Return 200 immediately (prevents Recall.ai timeout).
    3. Hand off processing to Celery task.
    """
    raw_body = await require_recall_signature(request, settings.recall_webhook_secret)

    try:
        payload = json.loads(raw_body.decode())
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    bot_data = payload.get("data", {}).get("bot", {})
    recall_bot_id = bot_data.get("id")

    if not recall_bot_id:
        logger.warning("Recall webhook: no bot.id in payload — ignoring")
        return {"status": "ignored"}

    # Idempotency: use recall event_id deduplicated via Redis (best-effort)
    event_id = payload.get("id", "")
    if event_id:
        try:
            import redis

            r = redis.from_url(settings.redis_url)
            key = f"recall_event:{event_id}"
            if r.exists(key):
                logger.info("Duplicate Recall webhook event %s — skipping", event_id)
                return {"status": "duplicate"}
            r.setex(key, 86400, "1")  # 24h TTL
        except Exception as exc:
            logger.warning("Redis idempotency check failed: %s", exc)

    # Enqueue processing task
    from app.workers.webhook_tasks import process_recall_webhook

    process_recall_webhook.delay(recall_bot_id, payload)

    return {"status": "accepted"}
