"""
auth-svc — Login endpoints.

POST /auth/login/email
POST /auth/login/oauth
POST /auth/login/phone/start
POST /auth/login/phone/verify
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.params import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Identity, Session, User
from app.schemas.auth import (
    LoginEmailRequest,
    LoginOAuthRequest,
    LoginPhoneStartRequest,
    LoginPhoneVerifyRequest,
    PhoneOtpSentResponse,
    TokenPair,
)
from app.services import brute_force, oauth, otp, password, tokens
from colab_common.db import get_session
from colab_common.errors import AuthError
from colab_common.events import enqueue_outbox
from colab_common.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/auth/login", tags=["login"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")


async def _issue_token_pair(db: AsyncSession, user: User, ip: str, user_agent: str) -> TokenPair:
    session_id = str(uuid.uuid4())
    refresh_token, refresh_jti = await tokens.mint_refresh_token(str(user.id), session_id)

    # Check if identity_verified (query identity-svc state via DB join — cross-svc read)
    # For now, default False; identity-svc will update via event
    access_token = await tokens.mint_access_token(
        str(user.id),
        session_id,
        email_verified=user.email_verified_at is not None,
        identity_verified=False,
    )

    refresh_hash = tokens.hash_token_str(refresh_token)
    db_session = Session(
        id=uuid.UUID(session_id),
        user_id=user.id,
        refresh_token_hash=refresh_hash,
        refresh_jti=refresh_jti,
        ip=ip,
        user_agent=user_agent,
    )
    db.add(db_session)

    # Update last_login_at
    user.last_login_at = datetime.now(UTC)

    return TokenPair(user_id=user.id, access_token=access_token, refresh_token=refresh_token)


@router.post("/email", response_model=TokenPair)
async def login_email(
    body: LoginEmailRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> TokenPair:
    """Email + password login with brute-force protection."""
    ip = _client_ip(request)

    await enforce_rate_limit(f"rl:login:ip:{ip}", capacity=10, refill_per_sec=10 / 60, retry_after=60)
    await brute_force.check_login_locked(body.email, ip)

    user = await db.scalar(select(User).where(User.email == body.email))

    if user is None or user.password_hash is None:
        # Record attempt even if user doesn't exist to avoid email enumeration
        await brute_force.record_failed_login(body.email, ip)
        raise AuthError("Invalid email or password.")

    if not user.is_active:
        raise AuthError("Account is deactivated. Contact support.")

    matched = await password.verify_password(user.password_hash, body.password)
    if not matched:
        await brute_force.record_failed_login(body.email, ip)
        raise AuthError("Invalid email or password.")

    # Success — clear counters
    await brute_force.clear_failed_logins(body.email, ip)

    # Rehash if parameters changed
    if await password.needs_rehash(user.password_hash):
        user.password_hash = await password.hash_password(body.password)

    user_agent = request.headers.get("User-Agent", "")[:512]
    return await _issue_token_pair(db, user, ip, user_agent)


@router.post("/oauth", response_model=TokenPair)
async def login_oauth(
    body: LoginOAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> TokenPair:
    """Apple or Google login. Creates account on first OAuth login."""
    ip = _client_ip(request)
    await enforce_rate_limit(f"rl:login:oauth:{ip}", capacity=30, refill_per_sec=0.5, retry_after=60)

    if body.provider == "apple":
        claims = await oauth.verify_apple_id_token(body.id_token, nonce=body.nonce)
    else:
        claims = await oauth.verify_google_id_token(body.id_token)

    provider_subject = claims["provider_subject"]

    identity = await db.scalar(
        select(Identity).where(
            Identity.provider == body.provider, Identity.provider_subject == provider_subject
        )
    )
    if identity is None:
        raise AuthError("No account found. Please sign up first.")

    user = await db.get(User, identity.user_id)
    if user is None or not user.is_active:
        raise AuthError("Account not found or deactivated.")

    user_agent = request.headers.get("User-Agent", "")[:512]
    return await _issue_token_pair(db, user, ip, user_agent)


@router.post("/phone/start", response_model=PhoneOtpSentResponse)
async def login_phone_start(
    body: LoginPhoneStartRequest,
    request: Request,
) -> PhoneOtpSentResponse:
    """Send phone OTP for login."""
    ip = _client_ip(request)
    await enforce_rate_limit(f"rl:otp:phone:{body.phone}", capacity=1, refill_per_sec=1 / 60, retry_after=60)
    await otp.send_phone_otp(body.phone, ip)
    return PhoneOtpSentResponse(phone=body.phone)


@router.post("/phone/verify", response_model=TokenPair)
async def login_phone_verify(
    body: LoginPhoneVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> TokenPair:
    """Verify OTP and issue tokens for phone login."""
    ip = _client_ip(request)

    matched = await otp.verify_phone_otp(body.phone, body.code)
    if not matched:
        raise AuthError("Invalid OTP code.")

    identity = await db.scalar(
        select(Identity).where(Identity.provider == "phone", Identity.provider_subject == body.phone)
    )
    if identity is None:
        raise AuthError("No account found for this phone number.")

    user = await db.get(User, identity.user_id)
    if user is None or not user.is_active:
        raise AuthError("Account not found or deactivated.")

    user_agent = request.headers.get("User-Agent", "")[:512]
    return await _issue_token_pair(db, user, ip, user_agent)
