"""
identity-svc — Identity verification endpoints.

POST /identity/inquiry/start     → creates Persona inquiry, returns session token
GET  /identity/verification      → current IdentityVerification state
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity_verification import IdentityVerification
from app.schemas.identity import IdentityVerificationOut, InquiryStartResponse
from app.services import persona
from colab_common.auth import AuthUser, require_user
from colab_common.db import get_session
from colab_common.errors import ServiceUnavailableError
from colab_common.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/identity", tags=["identity"])


@router.post("/inquiry/start", response_model=InquiryStartResponse)
async def inquiry_start(
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> InquiryStartResponse:
    """
    Start or resume a Persona inquiry for the authenticated user.
    Returns the inquiry_id and a one-time session token for the RN SDK.
    """
    await enforce_rate_limit(
        f"rl:persona:inquiry:{user.user_id}", capacity=3, refill_per_sec=3 / 3600, retry_after=3600
    )

    # Check for existing non-completed verification
    existing = await db.scalar(
        select(IdentityVerification).where(
            IdentityVerification.user_id == uuid.UUID(user.user_id)
        )
    )

    if existing and existing.status in ("approved", "declined"):
        # Already finalized — return existing inquiry info with a fresh session token
        if existing.persona_inquiry_id:
            try:
                session_token = await persona.get_session_token(existing.persona_inquiry_id)
            except ServiceUnavailableError:
                session_token = ""
            return InquiryStartResponse(
                persona_inquiry_id=existing.persona_inquiry_id,
                persona_session_token=session_token,
            )

    # Create new Persona inquiry
    inquiry_id = await persona.create_inquiry(user.user_id)
    session_token = await persona.get_session_token(inquiry_id)

    if existing:
        # Update existing row
        existing.persona_inquiry_id = inquiry_id
        existing.status = "pending"
    else:
        iv = IdentityVerification(
            user_id=uuid.UUID(user.user_id),
            persona_inquiry_id=inquiry_id,
            status="pending",
        )
        db.add(iv)

    return InquiryStartResponse(
        persona_inquiry_id=inquiry_id,
        persona_session_token=session_token,
    )


@router.get("/verification", response_model=IdentityVerificationOut)
async def get_verification(
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> IdentityVerificationOut:
    """Return the current IdentityVerification state for the authenticated user."""
    iv = await db.scalar(
        select(IdentityVerification).where(
            IdentityVerification.user_id == uuid.UUID(user.user_id)
        )
    )

    if iv is None:
        # Return a synthetic "not started" record
        now = datetime.now(UTC)
        return IdentityVerificationOut(
            user_id=uuid.UUID(user.user_id),
            persona_inquiry_id=None,
            status="pending",
            face_age_signal=None,
            decision_at=None,
            created_at=now,
            updated_at=now,
        )

    return IdentityVerificationOut.model_validate(iv)
