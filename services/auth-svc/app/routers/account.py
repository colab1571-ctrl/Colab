"""
auth-svc — Account management endpoints.

POST /auth/account/email/change/start
POST /auth/account/email/change/finish
POST /auth/account/phone/change/start
POST /auth/account/phone/change/finish
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import MagicLink, User
from app.schemas.auth import (
    EmailChangeFinishRequest,
    EmailChangeFinishResponse,
    EmailChangeStartRequest,
    EmailChangeStartResponse,
    PhoneChangeFinishRequest,
    PhoneChangeFinishResponse,
    PhoneChangeStartRequest,
    PhoneChangeStartResponse,
)
from app.services import email_sender, otp
from colab_common.auth import AuthUser, require_user
from colab_common.db import get_session
from colab_common.errors import AuthError, ConflictError
from colab_common.events import enqueue_outbox
from colab_common.rate_limit import enforce_rate_limit
from colab_common.settings import get_settings

router = APIRouter(prefix="/auth/account", tags=["account"])


@router.post("/email/change/start", response_model=EmailChangeStartResponse)
async def email_change_start(
    body: EmailChangeStartRequest,
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> EmailChangeStartResponse:
    """Start email change — sends verification to the new address."""
    settings = get_settings()
    await enforce_rate_limit(f"rl:email_change:{user.user_id}", capacity=3, refill_per_sec=3 / 3600, retry_after=3600)

    # Check new email not already taken
    existing = await db.scalar(select(User).where(User.email == body.new_email))
    if existing:
        raise ConflictError("That email address is already registered.")

    # Invalidate any existing email_change magic links for this user
    old_links = await db.scalars(
        select(MagicLink).where(
            MagicLink.user_id == uuid.UUID(user.user_id),
            MagicLink.purpose == "email_change",
            MagicLink.consumed_at.is_(None),
        )
    )
    for ml in old_links:
        ml.consumed_at = datetime.now(UTC)

    tok, tok_hash = otp.generate_magic_link_token()
    otp_code, otp_hash = otp.generate_otp_pair()
    expiry = otp.magic_link_expiry(15)

    ml = MagicLink(
        user_id=uuid.UUID(user.user_id),
        purpose="email_change",
        token_hash=tok_hash,
        otp_hash=otp_hash,
        new_value=body.new_email,
        expires_at=expiry,
    )
    db.add(ml)
    await db.flush()

    await email_sender.send_email_change_verification(body.new_email, tok, otp_code, settings.app_domain)
    return EmailChangeStartResponse()


@router.post("/email/change/finish", response_model=EmailChangeFinishResponse)
async def email_change_finish(
    body: EmailChangeFinishRequest,
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> EmailChangeFinishResponse:
    """Consume token/OTP and apply the email change."""
    if not body.token and not body.code:
        from colab_common.errors import ValidationError

        raise ValidationError("Either token or code is required.")

    ml: MagicLink | None = None
    if body.token:
        tok_hash = hashlib.sha256(body.token.encode()).hexdigest()
        ml = await db.scalar(
            select(MagicLink).where(
                MagicLink.token_hash == tok_hash,
                MagicLink.purpose == "email_change",
                MagicLink.user_id == uuid.UUID(user.user_id),
                MagicLink.consumed_at.is_(None),
            )
        )
    elif body.code:
        otp_hash = hashlib.sha256(body.code.encode()).hexdigest()
        ml = await db.scalar(
            select(MagicLink).where(
                MagicLink.otp_hash == otp_hash,
                MagicLink.purpose == "email_change",
                MagicLink.user_id == uuid.UUID(user.user_id),
                MagicLink.consumed_at.is_(None),
            )
        )

    if ml is None:
        raise AuthError("Invalid or expired token.")

    now = datetime.now(UTC)
    if ml.expires_at.replace(tzinfo=UTC) < now:
        raise AuthError("Token has expired. Start the email change again.")

    db_user = await db.get(User, uuid.UUID(user.user_id))
    if db_user is None:
        raise AuthError("User not found.")

    new_email = ml.new_value
    # Final uniqueness check before applying
    if await db.scalar(select(User).where(User.email == new_email)):
        ml.consumed_at = now
        raise ConflictError("Email address is no longer available.")

    db_user.email = new_email
    db_user.email_verified_at = now
    ml.consumed_at = now

    await enqueue_outbox(db, "user.email_changed", {"user_id": user.user_id, "new_email": new_email})
    return EmailChangeFinishResponse()


@router.post("/phone/change/start", response_model=PhoneChangeStartResponse)
async def phone_change_start(
    body: PhoneChangeStartRequest,
    request: Request,
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> PhoneChangeStartResponse:
    """Start phone change — send OTP to the new number."""
    ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(f"rl:phone_change:{user.user_id}", capacity=3, refill_per_sec=3 / 3600, retry_after=3600)

    existing = await db.scalar(select(User).where(User.phone == body.new_phone))
    if existing:
        raise ConflictError("That phone number is already registered.")

    await otp.send_phone_otp(body.new_phone, ip)
    return PhoneChangeStartResponse()


@router.post("/phone/change/finish", response_model=PhoneChangeFinishResponse)
async def phone_change_finish(
    body: PhoneChangeFinishRequest,
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> PhoneChangeFinishResponse:
    """Verify OTP and apply phone change."""
    matched = await otp.verify_phone_otp(body.new_phone, body.code)
    if not matched:
        raise AuthError("Invalid OTP.")

    db_user = await db.get(User, uuid.UUID(user.user_id))
    if db_user is None:
        raise AuthError("User not found.")

    db_user.phone = body.new_phone
    db_user.phone_verified_at = datetime.now(UTC)

    await enqueue_outbox(db, "user.phone_changed", {"user_id": user.user_id, "new_phone": body.new_phone})
    return PhoneChangeFinishResponse()
