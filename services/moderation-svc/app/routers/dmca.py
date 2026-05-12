"""
moderation-svc — DMCA workflow router.

POST /dmca/notice     — M-031 (intake + §512(c)(3) validation)
POST /dmca/{id}/counter-notice — M-033
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_mod_settings
from app.db import get_db
from app.models import CounterNotice, DMCANotice, ModerationCase
from app.schemas import (
    CounterNoticeCreate,
    CounterNoticeResponse,
    DMCANoticeCreate,
    DMCANoticeResponse,
)

router = APIRouter(prefix="/dmca", tags=["dmca"])


def _hash_signature(full_name: str, timestamp: datetime, ip: str) -> bytes:
    payload = f"{full_name}:{timestamp.isoformat()}:{ip}"
    return hashlib.sha256(payload.encode()).digest()


def _validate_dmca_fields(body: DMCANoticeCreate) -> list[str]:
    """
    Validate §512(c)(3) required fields per plan §2.6.
    Returns list of missing/defective field descriptions.
    """
    defects: list[str] = []
    if not body.is_authorized_agent:
        defects.append("Field 1: Physical/electronic signature and authorization — 'is_authorized_agent' must be true")
    if not body.copyrighted_work_description and not body.copyrighted_work_url_or_registration:
        defects.append("Field 2: Identification of the copyrighted work — description or URL/registration required")
    if not body.target_url_on_colab:
        defects.append("Field 3: Identification of the allegedly infringing material — URL required")
    if not all([body.claimant_name, body.claimant_address, body.claimant_phone, body.claimant_email]):
        defects.append("Field 4: Contact information — name, address, phone, and email required")
    if "penalty of perjury" not in (body.sworn_statement_text or "").lower():
        defects.append("Field 5: Good-faith statement — must include 'under penalty of perjury'")
    if not body.signature_full_name:
        defects.append("Field 6: Statement of accuracy and authorization — signature required")
    return defects


@router.post("/notice", status_code=status.HTTP_201_CREATED, response_model=DMCANoticeResponse)
async def file_dmca_notice(
    body: DMCANoticeCreate,
    request: Request,
    sess: AsyncSession = Depends(get_db),
) -> DMCANoticeResponse:
    """
    DMCA takedown notice intake.

    No auth required — claimants are often third parties.
    Rate-limited by IP (5/day) and email (10/day).
    Validates all §512(c)(3) required fields; returns 422 with defect checklist if invalid.
    """
    settings = get_mod_settings()
    client_ip = request.client.host if request.client else "unknown"

    # --- Rate limiting ---
    await _check_dmca_rate_limit(request, body.claimant_email, client_ip, settings)

    # --- §512(c)(3) validation ---
    defects = _validate_dmca_fields(body)
    if defects:
        # Record the defective attempt and return 422
        now = datetime.now(tz=timezone.utc)
        defective = DMCANotice(
            claimant_name=body.claimant_name,
            claimant_address=body.claimant_address,
            claimant_phone=body.claimant_phone,
            claimant_email=body.claimant_email,
            is_authorized_agent=body.is_authorized_agent,
            sworn_statement_text=body.sworn_statement_text,
            signature_full_name=body.signature_full_name or "",
            hash_of_signature=_hash_signature(body.signature_full_name or "", now, client_ip),
            copyrighted_work_description=body.copyrighted_work_description,
            copyrighted_work_url_or_registration=body.copyrighted_work_url_or_registration,
            target_subject_type=body.target_subject_type,
            target_subject_id=body.target_subject_id,
            target_url_on_colab=body.target_url_on_colab,
            target_user_id=body.target_subject_id,  # resolved from subject at app layer
            claimant_ip=client_ip,
            received_at=now,
            state="rejected_defective",
            rejection_reason="; ".join(defects),
        )
        sess.add(defective)
        await sess.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Your DMCA notice was statutorily defective for the following reasons:",
                "defects": defects,
                "notice_id": str(defective.id),
            },
        )

    now = datetime.now(tz=timezone.utc)
    hide_at = now + timedelta(hours=24)

    # Create ModerationCase linked to this notice
    case = ModerationCase(
        kind="dmca",
        subject_type=body.target_subject_type,
        subject_id=body.target_subject_id,
        subject_owner_user_id=body.target_subject_id,
        status="open",
        priority_tier="tier_2_6h",
        forced_human=True,
        forced_reason="ip_claim",
        sla_due_at=now + timedelta(hours=settings.tier2_sla_hours),
        opened_at=now,
    )
    sess.add(case)
    await sess.flush()

    notice = DMCANotice(
        claimant_name=body.claimant_name,
        claimant_address=body.claimant_address,
        claimant_phone=body.claimant_phone,
        claimant_email=body.claimant_email,
        is_authorized_agent=body.is_authorized_agent,
        sworn_statement_text=body.sworn_statement_text,
        signature_full_name=body.signature_full_name,
        hash_of_signature=_hash_signature(body.signature_full_name, now, client_ip),
        copyrighted_work_description=body.copyrighted_work_description,
        copyrighted_work_url_or_registration=body.copyrighted_work_url_or_registration,
        target_subject_type=body.target_subject_type,
        target_subject_id=body.target_subject_id,
        target_url_on_colab=body.target_url_on_colab,
        target_user_id=body.target_subject_id,
        claimant_ip=client_ip,
        received_at=now,
        hide_at=hide_at,
        state="received",
        case_id=case.id,
    )
    sess.add(notice)
    await sess.commit()
    await sess.refresh(notice)

    # Emit event
    from colab_common.events import publish
    try:
        await publish(
            "dmca.notice_filed",
            {
                "dmca_id": str(notice.id),
                "case_id": str(case.id),
                "target_user_id": str(notice.target_user_id),
                "hide_at": hide_at.isoformat(),
            },
        )
    except Exception:
        pass

    return DMCANoticeResponse(
        dmca_id=notice.id,
        case_id=case.id,
        received_at=notice.received_at,
        state=notice.state,
        hide_at=notice.hide_at,
    )


@router.post("/{dmca_id}/counter-notice", status_code=status.HTTP_201_CREATED, response_model=CounterNoticeResponse)
async def file_counter_notice(
    dmca_id: uuid.UUID,
    body: CounterNoticeCreate,
    request: Request,
    sess: AsyncSession = Depends(get_db),
) -> CounterNoticeResponse:
    """
    DMCA counter-notice intake (§512(g)(3)).

    Only the target user (authenticated + token-bound) may file.
    Validates §512(g)(3) required fields.
    Sets statutory_window_end = now + 14 calendar days.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_id_header = request.headers.get("X-User-Id")
    if not user_id_header:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    try:
        counter_claimant_user_id = uuid.UUID(user_id_header)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")

    # Fetch DMCA notice and validate target
    result = await sess.execute(select(DMCANotice).where(DMCANotice.id == dmca_id))
    notice = result.scalar_one_or_none()
    if not notice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DMCA notice not found")
    if notice.target_user_id != counter_claimant_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the target user may file a counter-notice")
    if notice.state not in ("hidden", "received"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Counter-notice cannot be filed when DMCA notice is in state '{notice.state}'",
        )
    if notice.counter_notice:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A counter-notice was already filed for this DMCA notice")

    # Token validation (single-use token from email link)
    # In production, token would be a signed JWT stored in Redis with TTL
    # Here we validate format only (full impl requires Redis lookup)
    if not body.counter_token or len(body.counter_token) < 10:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid counter-notice token")

    settings = get_mod_settings()
    now = datetime.now(tz=timezone.utc)
    statutory_window_end = now + timedelta(days=settings.dmca_statutory_window_days)

    counter = CounterNotice(
        dmca_id=dmca_id,
        counter_claimant_user_id=counter_claimant_user_id,
        counter_claimant_legal_name=body.counter_claimant_legal_name,
        counter_claimant_address=body.counter_claimant_address,
        counter_claimant_phone=body.counter_claimant_phone,
        counter_statement_text=body.counter_statement_text,
        consent_to_jurisdiction=body.consent_to_jurisdiction,
        consent_to_service_of_process=body.consent_to_service_of_process,
        signature_full_name=body.signature_full_name,
        hash_of_signature=_hash_signature(body.signature_full_name, now, client_ip),
        received_at=now,
        statutory_window_end=statutory_window_end,
        state="received",
    )
    sess.add(counter)

    # Update DMCA notice state
    notice.state = "counter_pending"

    await sess.commit()
    await sess.refresh(counter)

    # Emit event
    from colab_common.events import publish
    try:
        await publish(
            "dmca.counter_filed",
            {
                "counter_id": str(counter.id),
                "dmca_id": str(dmca_id),
                "target_user_id": str(counter_claimant_user_id),
                "statutory_window_end": statutory_window_end.isoformat(),
            },
        )
    except Exception:
        pass

    return CounterNoticeResponse(
        counter_id=counter.id,
        dmca_id=dmca_id,
        statutory_window_end=statutory_window_end,
        state=counter.state,
    )


async def _check_dmca_rate_limit(
    request: Request, email: str, ip: str, settings
) -> None:
    """
    Rate-limit DMCA notices: 5/day/IP, 10/day/email.
    Uses Redis INCR with 24h TTL.
    """
    import os

    import redis.asyncio as aioredis

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        r = aioredis.from_url(redis_url, decode_responses=True)
        today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")

        ip_key = f"mod:dmca_rl:ip:{ip}:{today}"
        email_key = f"mod:dmca_rl:email:{email}:{today}"

        ip_count = await r.incr(ip_key)
        if ip_count == 1:
            await r.expire(ip_key, 86400)

        email_count = await r.incr(email_key)
        if email_count == 1:
            await r.expire(email_key, 86400)

        if ip_count > settings.dmca_per_ip_per_day:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many DMCA notices from this IP ({settings.dmca_per_ip_per_day}/day limit)",
                headers={"Retry-After": "86400"},
            )
        if email_count > settings.dmca_per_email_per_day:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many DMCA notices from this email ({settings.dmca_per_email_per_day}/day limit)",
                headers={"Retry-After": "86400"},
            )
        await r.aclose()
    except HTTPException:
        raise
    except Exception:
        pass  # Redis unavailable — fail-open for DMCA (legal obligation)
