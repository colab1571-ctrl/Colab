"""
auth-svc — Email verification endpoints.

POST /auth/email/verify/start
POST /auth/email/verify/finish
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import MagicLink, User
from app.schemas.auth import (
    EmailVerifyFinishRequest,
    EmailVerifyFinishResponse,
    EmailVerifyStartRequest,
    EmailVerifyStartResponse,
)
from app.services import email_sender, otp
from colab_common.auth import require_user
from colab_common.db import get_session
from colab_common.errors import AuthError, NotFoundError, ValidationError
from colab_common.events import enqueue_outbox
from colab_common.rate_limit import enforce_rate_limit
from colab_common.settings import get_settings

router = APIRouter(prefix="/auth/email", tags=["email-verify"])


@router.post("/verify/start", response_model=EmailVerifyStartResponse)
async def verify_start(
    body: EmailVerifyStartRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> EmailVerifyStartResponse:
    """Send (or re-send) a verification email."""
    settings = get_settings()
    ip = request.client.host if request.client else "unknown"

    await enforce_rate_limit(
        f"rl:email_verify:{body.email}", capacity=3, refill_per_sec=3 / 600, retry_after=600
    )

    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None:
        # Do not leak whether email exists
        return EmailVerifyStartResponse()

    if user.email_verified_at is not None:
        return EmailVerifyStartResponse(message="Email is already verified.")

    # Invalidate any existing unused magic links for this user/purpose
    existing_links = await db.scalars(
        select(MagicLink).where(
            MagicLink.user_id == user.id,
            MagicLink.purpose == "email_verify",
            MagicLink.consumed_at.is_(None),
        )
    )
    for link in existing_links:
        link.consumed_at = datetime.now(UTC)

    tok, tok_hash = otp.generate_magic_link_token()
    otp_code, otp_hash = otp.generate_otp_pair()
    expiry = otp.magic_link_expiry(15)

    ml = MagicLink(
        user_id=user.id,
        purpose="email_verify",
        token_hash=tok_hash,
        otp_hash=otp_hash,
        expires_at=expiry,
    )
    db.add(ml)
    await db.flush()

    await email_sender.send_email_verification(body.email, tok, otp_code, settings.app_domain)

    return EmailVerifyStartResponse()


@router.post("/verify/finish", response_model=EmailVerifyFinishResponse)
async def verify_finish(
    body: EmailVerifyFinishRequest,
    db: AsyncSession = Depends(get_session),
) -> EmailVerifyFinishResponse:
    """Consume magic-link token or 6-digit OTP to mark email verified."""
    if not body.token and not body.code:
        raise ValidationError("Either token or code is required.")

    # Find matching magic link
    ml: MagicLink | None = None

    if body.token:
        # Hash and lookup
        import hashlib

        token_hash = hashlib.sha256(body.token.encode()).hexdigest()
        ml = await db.scalar(
            select(MagicLink).where(
                MagicLink.token_hash == token_hash,
                MagicLink.purpose == "email_verify",
                MagicLink.consumed_at.is_(None),
            )
        )
    elif body.code:
        import hashlib

        otp_hash = hashlib.sha256(body.code.encode()).hexdigest()
        ml = await db.scalar(
            select(MagicLink).where(
                MagicLink.otp_hash == otp_hash,
                MagicLink.purpose == "email_verify",
                MagicLink.consumed_at.is_(None),
            )
        )

    if ml is None:
        raise AuthError("Invalid or already used verification token.")

    now = datetime.now(UTC)
    if ml.expires_at.replace(tzinfo=UTC) < now:
        raise AuthError("Verification link has expired. Request a new one.")

    # Mark consumed
    ml.consumed_at = now

    # Mark user verified
    user = await db.get(User, ml.user_id)
    if user is None:
        raise NotFoundError("User")

    user.email_verified_at = now
    await enqueue_outbox(db, "user.email_verified", {"user_id": str(user.id), "email": user.email})

    return EmailVerifyFinishResponse()
