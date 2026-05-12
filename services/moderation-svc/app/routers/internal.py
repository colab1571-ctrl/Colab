"""
moderation-svc — Internal scan APIs (service-to-service, mTLS in cluster).

POST /internal/scan/text   — synchronous (§007 chat send path)
POST /internal/scan/image  — synchronous (pre-publish gate)
POST /internal/scan/audio  — async (returns job_id)
POST /internal/scan/video  — async (Rekognition async natively)
GET  /internal/user/{user_id}/state — current ban/mute state for §007 chat gate

M-008
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_mod_settings
from app.db import get_db
from app.models import ModerationAction, ModerationCase, ModScanLog
from app.schemas import (
    AsyncScanResponse,
    AudioScanRequest,
    ImageScanRequest,
    ScanResponse,
    TextScanRequest,
    UserStateResponse,
    VideoScanRequest,
)
from app.workers.scan_tasks import (
    build_routing_result,
    scan_openai_text,
    scan_rekognition_image,
    start_rekognition_video,
    scan_chromaprint,
    scan_phash,
    scan_semdup,
)

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def _require_internal(request: Request) -> None:
    """Block external callers — in production, mTLS + gateway strip external."""
    # Gateway sets X-Internal-Service header for legitimate callers
    service = request.headers.get("X-Internal-Service", "")
    if not service and os.environ.get("ENV", "local") not in ("local", "dev"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Internal endpoint")


async def _persist_scan_log(
    sess: AsyncSession,
    subject_type: str,
    subject_id: uuid.UUID,
    tool: str,
    score: float | None,
    raw: dict,
    idempotency_key: str | None = None,
) -> None:
    log = ModScanLog(
        subject_type=subject_type,
        subject_id=subject_id,
        idempotency_key=idempotency_key,
        tool=tool,
        score=score,
        raw_response=raw,
    )
    sess.add(log)


async def _create_case_from_routing(
    sess: AsyncSession,
    routing: dict,
    ctx: dict,
    idempotency_key: str | None = None,
) -> ModerationCase | None:
    """Create a ModerationCase if the routing decision warrants it (score >= tier1)."""
    if routing["tier"] == "tier_0_allow" and not routing["forced_human"]:
        return None

    settings = get_mod_settings()
    now = datetime.now(tz=timezone.utc)

    sla_hours = routing.get("sla_hours") or settings.tier1_sla_hours
    sla_due = now + timedelta(hours=sla_hours)

    # Check idempotency
    if idempotency_key:
        result = await sess.execute(
            select(ModerationCase).where(ModerationCase.idempotency_key == idempotency_key)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    case = ModerationCase(
        kind="auto",
        subject_type=ctx.get("subject_type", "msg"),
        subject_id=uuid.UUID(ctx["subject_id"]) if isinstance(ctx.get("subject_id"), str) else ctx.get("subject_id"),
        subject_owner_user_id=uuid.UUID(ctx["owner_user_id"]) if isinstance(ctx.get("owner_user_id"), str) else ctx.get("owner_user_id"),
        score=routing["score"],
        scores_breakdown=routing.get("breakdown", {}),
        forced_human=routing["forced_human"],
        forced_reason=routing.get("forced_reason"),
        status="open",
        priority_tier=routing["tier"],
        sla_due_at=sla_due,
        opened_at=now,
        idempotency_key=idempotency_key,
    )
    sess.add(case)
    return case


def _decision_label(action: str) -> str:
    mapping = {
        "allow_log": "allow",
        "soft_warn_user_queue": "soft_warn",
        "hide_content_queue": "hide",
        "auto_hide_temp_mute_queue": "auto_hide_mute",
    }
    return mapping.get(action, "allow")


@router.post("/scan/text", response_model=ScanResponse)
async def scan_text(
    body: TextScanRequest,
    request: Request,
    sess: AsyncSession = Depends(get_db),
) -> ScanResponse:
    """
    Synchronous text scan. Used by chat-svc on every message send.
    Runs OpenAI omni-mod + semantic dup in the same request (parallel via Celery chord,
    but for sync path we call task.apply() directly in-process).

    Accepts an idempotency_key in ctx to prevent duplicate case creation on retries.
    """
    _require_internal(request)

    idem_key = body.ctx.get("idempotency_key")

    # Run tools synchronously (Celery .apply() runs in-process without worker)
    openai_raw = scan_openai_text.apply(
        kwargs={"text": body.text, "ctx": body.ctx}
    ).get(timeout=8)

    semdup_raw = scan_semdup.apply(
        kwargs={"text": body.text, "ctx": body.ctx}
    ).get(timeout=10)

    routing = build_routing_result(
        openai_result=openai_raw,
        rekognition_result=None,
        phash_result=None,
        chromaprint_result=None,
        semdup_result=semdup_raw,
    )

    # Persist scan log
    subject_id_val = body.ctx.get("subject_id")
    subject_id = uuid.UUID(subject_id_val) if subject_id_val else uuid.uuid4()
    await _persist_scan_log(
        sess,
        body.ctx.get("subject_type", "msg"),
        subject_id,
        "openai_mod+semdup",
        routing["score"],
        {"openai": openai_raw, "semdup": semdup_raw},
        idem_key,
    )

    case = await _create_case_from_routing(sess, routing, body.ctx, idem_key)
    await sess.commit()

    return ScanResponse(
        score=routing["score"],
        breakdown=routing["breakdown"],
        decision=_decision_label(routing["action"]),
        case_id=case.id if case else None,
        action=routing["action"],
        tier=routing["tier"],
        forced_human=routing["forced_human"],
    )


@router.post("/scan/image", response_model=ScanResponse)
async def scan_image(
    body: ImageScanRequest,
    request: Request,
    sess: AsyncSession = Depends(get_db),
) -> ScanResponse:
    """
    Synchronous image scan: Rekognition + pHash.
    Called by media-svc after S3 upload completes.
    """
    _require_internal(request)
    settings = get_mod_settings()
    bucket = body.s3_bucket or os.environ.get("S3_MEDIA_BUCKET", "colab-media")

    rek_raw = scan_rekognition_image.apply(
        kwargs={"s3_key": body.s3_key, "s3_bucket": bucket, "ctx": body.ctx}
    ).get(timeout=15)

    phash_raw = scan_phash.apply(
        kwargs={"s3_key": body.s3_key, "s3_bucket": bucket, "ctx": body.ctx}
    ).get(timeout=10)

    routing = build_routing_result(
        openai_result={"flagged": False, "category_scores": {}, "flagged_categories": []},
        rekognition_result=rek_raw,
        phash_result=phash_raw,
        chromaprint_result=None,
        semdup_result=None,
    )

    subject_id_val = body.ctx.get("subject_id")
    subject_id = uuid.UUID(subject_id_val) if subject_id_val else uuid.uuid4()
    await _persist_scan_log(sess, body.ctx.get("subject_type", "portfolio_item"), subject_id, "rekognition+phash", routing["score"], {"rekognition": rek_raw, "phash": phash_raw})
    case = await _create_case_from_routing(sess, routing, body.ctx)
    await sess.commit()

    return ScanResponse(
        score=routing["score"],
        breakdown=routing["breakdown"],
        decision=_decision_label(routing["action"]),
        case_id=case.id if case else None,
        action=routing["action"],
        tier=routing["tier"],
        forced_human=routing["forced_human"],
    )


@router.post("/scan/audio", response_model=AsyncScanResponse)
async def scan_audio(
    body: AudioScanRequest,
    request: Request,
) -> AsyncScanResponse:
    """
    Async audio scan via Chromaprint. Returns job_id.
    Result delivered via callback_url webhook when Celery task completes.
    """
    _require_internal(request)
    bucket = body.s3_bucket or os.environ.get("S3_MEDIA_BUCKET", "colab-media")
    task = scan_chromaprint.apply_async(
        kwargs={"s3_key": body.s3_key, "s3_bucket": bucket, "ctx": body.ctx}
    )
    return AsyncScanResponse(job_id=task.id)


@router.post("/scan/video", response_model=AsyncScanResponse)
async def scan_video(
    body: VideoScanRequest,
    request: Request,
) -> AsyncScanResponse:
    """
    Async video scan via Rekognition StartContentModeration.
    SNS notifies when complete; result collected by rekognition_video_result task.
    """
    _require_internal(request)
    bucket = body.s3_bucket or os.environ.get("S3_MEDIA_BUCKET", "colab-media")
    sns_arn = body.sns_topic_arn or os.environ.get("REKOGNITION_SNS_TOPIC_ARN", "")
    task = start_rekognition_video.apply_async(
        kwargs={
            "s3_key": body.s3_key,
            "s3_bucket": bucket,
            "sns_topic_arn": sns_arn,
            "ctx": body.ctx,
        }
    )
    return AsyncScanResponse(job_id=task.id)


@router.get("/user/{user_id}/state", response_model=UserStateResponse)
async def get_user_state(
    user_id: uuid.UUID,
    request: Request,
    sess: AsyncSession = Depends(get_db),
) -> UserStateResponse:
    """
    Returns current ban/mute state for a user. Used by chat-svc on every send.
    Redis-cached; DB fallback. <5ms P95 target.
    """
    _require_internal(request)

    # Check Redis first (set synchronously by action endpoint)
    import redis.asyncio as aioredis

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    is_banned = False
    is_muted = False
    mute_expires_at = None

    try:
        r = aioredis.from_url(redis_url, decode_responses=True)
        ban_val = await r.get(f"mod:user_state:banned:{user_id}")
        mute_val = await r.get(f"mod:user_state:muted:{user_id}")
        mute_exp_val = await r.get(f"mod:user_state:mute_expires:{user_id}")
        await r.aclose()

        is_banned = ban_val == "1"
        is_muted = mute_val == "1"
        if mute_exp_val:
            from datetime import datetime
            mute_expires_at = datetime.fromisoformat(mute_exp_val)
    except Exception:
        # Fall back to DB on Redis failure
        result = await sess.execute(
            select(ModerationAction)
            .where(ModerationAction.target_user_id == user_id)
            .where(ModerationAction.action_type.in_(["permanent_ban", "delete_account", "temp_mute_1h", "temp_mute_24h", "temp_mute_7d"]))
            .order_by(ModerationAction.created_at.desc())
            .limit(5)
        )
        actions = result.scalars().all()
        now = datetime.now(tz=timezone.utc)
        for action in actions:
            if action.action_type in ("permanent_ban", "delete_account"):
                is_banned = True
                break
            elif action.action_type.startswith("temp_mute_"):
                duration_map = {"temp_mute_1h": 1, "temp_mute_24h": 24, "temp_mute_7d": 168}
                hours = duration_map.get(action.action_type, 1)
                exp = action.created_at + timedelta(hours=hours)
                if exp > now:
                    is_muted = True
                    mute_expires_at = exp
                    break

    # Active cases count
    result = await sess.execute(
        select(ModerationCase)
        .where(
            ModerationCase.subject_owner_user_id == user_id,
            ModerationCase.status.in_(["open", "in_review"]),
        )
    )
    active_cases = result.scalars().all()

    return UserStateResponse(
        user_id=user_id,
        is_banned=is_banned,
        is_muted=is_muted,
        mute_expires_at=mute_expires_at,
        active_cases_count=len(active_cases),
    )
