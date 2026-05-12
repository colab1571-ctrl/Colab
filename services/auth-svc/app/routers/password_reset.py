"""
auth-svc — Password reset endpoints.

POST /auth/password/reset/start
POST /auth/password/reset/finish
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import MagicLink, User
from app.schemas.auth import (
    PasswordResetFinishRequest,
    PasswordResetFinishResponse,
    PasswordResetStartRequest,
    PasswordResetStartResponse,
)
from app.services import email_sender, otp, password
from colab_common.db import get_session
from colab_common.errors import AuthError, ValidationError
from colab_common.rate_limit import enforce_rate_limit
from colab_common.settings import get_settings

router = APIRouter(prefix="/auth/password", tags=["password"])


@router.post("/reset/start", response_model=PasswordResetStartResponse)
async def reset_start(
    body: PasswordResetStartRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> PasswordResetStartResponse:
    """Send password reset email. Always returns success (prevents email enumeration)."""
    settings = get_settings()
    await enforce_rate_limit(
        f"rl:pwd_reset:{body.email}", capacity=3, refill_per_sec=3 / 600, retry_after=600
    )

    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None:
        return PasswordResetStartResponse()

    # Invalidate existing reset links
    existing = await db.scalars(
        select(MagicLink).where(
            MagicLink.user_id == user.id,
            MagicLink.purpose == "password_reset",
            MagicLink.consumed_at.is_(None),
        )
    )
    for ml in existing:
        ml.consumed_at = datetime.now(UTC)

    tok, tok_hash = otp.generate_magic_link_token()
    otp_code, otp_hash = otp.generate_otp_pair()
    expiry = otp.magic_link_expiry(15)

    ml = MagicLink(
        user_id=user.id,
        purpose="password_reset",
        token_hash=tok_hash,
        otp_hash=otp_hash,
        expires_at=expiry,
    )
    db.add(ml)
    await db.flush()

    await email_sender.send_password_reset(body.email, tok, otp_code, settings.app_domain)

    return PasswordResetStartResponse()


@router.post("/reset/finish", response_model=PasswordResetFinishResponse)
async def reset_finish(
    body: PasswordResetFinishRequest,
    db: AsyncSession = Depends(get_session),
) -> PasswordResetFinishResponse:
    """Consume reset token and update password."""
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    ml = await db.scalar(
        select(MagicLink).where(
            MagicLink.token_hash == token_hash,
            MagicLink.purpose == "password_reset",
            MagicLink.consumed_at.is_(None),
        )
    )

    if ml is None:
        raise AuthError("Invalid or expired reset token.")

    now = datetime.now(UTC)
    if ml.expires_at.replace(tzinfo=UTC) < now:
        raise AuthError("Reset link has expired. Request a new one.")

    user = await db.get(User, ml.user_id)
    if user is None:
        raise AuthError("User not found.")

    await password.validate_password(body.new_password, email=user.email)
    user.password_hash = await password.hash_password(body.new_password)
    ml.consumed_at = now

    return PasswordResetFinishResponse()
