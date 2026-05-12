"""
auth-svc — Signup endpoints.

POST /auth/signup/email
POST /auth/signup/oauth
POST /auth/signup/phone
POST /auth/signup/phone/verify
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Identity, LegalAcceptance, Session, User
from app.schemas.auth import (
    PhoneOtpSentResponse,
    PhoneVerifyRequest,
    SignupEmailRequest,
    SignupOAuthRequest,
    SignupPhoneRequest,
    TokenPair,
)
from app.services import brute_force, email_sender, oauth, otp, password, tokens
from colab_common.db import get_session
from colab_common.errors import ConflictError, ValidationError
from colab_common.events import enqueue_outbox
from colab_common.rate_limit import enforce_rate_limit
from colab_common.settings import get_settings

router = APIRouter(prefix="/auth/signup", tags=["signup"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")


async def _record_legal_acceptances(
    session: AsyncSession,
    user_id: uuid.UUID,
    ip: str,
    tos_version: str,
    privacy_version: str,
    community_version: str,
) -> None:
    now = datetime.now(UTC)
    for doc_type, version in [
        ("tos", tos_version),
        ("privacy", privacy_version),
        ("community_guidelines", community_version),
    ]:
        session.add(LegalAcceptance(user_id=user_id, doc_type=doc_type, doc_version=version, accepted_at=now, ip=ip))


async def _issue_token_pair(session: AsyncSession, user: User, ip: str, user_agent: str) -> TokenPair:
    """Create a session row and issue access + refresh tokens."""
    session_id = str(uuid.uuid4())
    refresh_token, refresh_jti = await tokens.mint_refresh_token(str(user.id), session_id)
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
    session.add(db_session)
    return TokenPair(user_id=user.id, access_token=access_token, refresh_token=refresh_token)


@router.post("/email", response_model=TokenPair, status_code=201)
async def signup_email(
    body: SignupEmailRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> TokenPair:
    """Email + password signup. 18+ attestation enforced. Legal docs recorded."""
    settings = get_settings()
    ip = _client_ip(request)

    await enforce_rate_limit(f"rl:signup:email:{ip}", capacity=5, refill_per_sec=5 / 60, retry_after=60)

    # 18+ gate — the body schema enforces age_attestation=True via Literal[True]
    # so if we reach here, attestation is already confirmed by Pydantic.

    # Check email uniqueness
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise ConflictError("An account with this email already exists.")

    # Validate + hash password
    await password.validate_password(body.password, email=body.email)
    pw_hash = await password.hash_password(body.password)

    user = User(email=body.email, password_hash=pw_hash)
    db.add(user)
    await db.flush()  # get user.id

    await _record_legal_acceptances(
        db, user.id, ip, body.tos_version, body.privacy_version, body.community_version
    )

    # Issue tokens
    user_agent = request.headers.get("User-Agent", "")[:512]
    token_pair = await _issue_token_pair(db, user, ip, user_agent)

    # Enqueue outbox event
    await enqueue_outbox(db, "user.created", {"user_id": str(user.id), "email": user.email})

    # Send email verification async (fire-and-forget; real app queues via Celery)
    from app.routers import email_verify as ev_router

    # Schedule email verify — create the magic link
    tok, tok_hash = otp.generate_magic_link_token()
    otp_code, otp_hash = otp.generate_otp_pair()
    expiry = otp.magic_link_expiry(15)
    from app.models.user import MagicLink

    ml = MagicLink(
        user_id=user.id,
        purpose="email_verify",
        token_hash=tok_hash,
        otp_hash=otp_hash,
        expires_at=expiry,
    )
    db.add(ml)
    await db.flush()

    # Fire email (non-blocking in real app via Celery; sync here for simplicity)
    try:
        await email_sender.send_email_verification(
            body.email, tok, otp_code, settings.app_domain
        )
    except Exception:
        pass  # Email failure does not block signup

    return token_pair


@router.post("/oauth", response_model=TokenPair, status_code=201)
async def signup_oauth(
    body: SignupOAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> TokenPair:
    """Apple or Google Sign-In signup."""
    ip = _client_ip(request)
    await enforce_rate_limit(f"rl:signup:oauth:{ip}", capacity=30, refill_per_sec=0.5, retry_after=60)

    # Verify provider token
    if body.provider == "apple":
        claims = await oauth.verify_apple_id_token(body.id_token, nonce=body.nonce)
    else:
        claims = await oauth.verify_google_id_token(body.id_token)

    provider_subject = claims["provider_subject"]
    provider_email = claims.get("email", "")

    # Check for existing identity (re-login path)
    existing_identity = await db.scalar(
        select(Identity).where(
            Identity.provider == body.provider, Identity.provider_subject == provider_subject
        )
    )
    if existing_identity:
        raise ConflictError("Account already exists. Please log in instead.")

    # Check for existing user with same email (merge by email when email_verified)
    user: User | None = None
    if provider_email and claims.get("email_verified"):
        user = await db.scalar(select(User).where(User.email == provider_email.lower()))

    if user is None:
        email_val = provider_email.lower() if provider_email else None
        user = User(
            email=email_val,
            email_verified_at=datetime.now(UTC) if claims.get("email_verified") else None,
        )
        db.add(user)
        await db.flush()
        await enqueue_outbox(db, "user.created", {"user_id": str(user.id), "email": user.email})

    identity = Identity(
        user_id=user.id,
        provider=body.provider,
        provider_subject=provider_subject,
    )
    db.add(identity)

    await _record_legal_acceptances(
        db, user.id, ip, body.tos_version, body.privacy_version, body.community_version
    )

    user_agent = request.headers.get("User-Agent", "")[:512]
    return await _issue_token_pair(db, user, ip, user_agent)


@router.post("/phone", response_model=PhoneOtpSentResponse)
async def signup_phone_start(
    body: SignupPhoneRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> PhoneOtpSentResponse:
    """Start phone signup — send OTP via SNS."""
    ip = _client_ip(request)
    await enforce_rate_limit(f"rl:otp:phone:{body.phone}", capacity=1, refill_per_sec=1 / 60, retry_after=60)

    existing = await db.scalar(select(User).where(User.phone == body.phone))
    if existing:
        raise ConflictError("An account with this phone number already exists.")

    await otp.send_phone_otp(body.phone, ip)
    return PhoneOtpSentResponse(phone=body.phone)


@router.post("/phone/verify", response_model=TokenPair, status_code=201)
async def signup_phone_verify(
    body: PhoneVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> TokenPair:
    """Verify phone OTP and complete signup."""
    ip = _client_ip(request)

    matched = await otp.verify_phone_otp(body.phone, body.code)
    if not matched:
        from colab_common.errors import AuthError

        raise AuthError("Invalid OTP code.")

    # Create user
    user = User(phone=body.phone, phone_verified_at=datetime.now(UTC))
    db.add(user)
    await db.flush()

    identity = Identity(user_id=user.id, provider="phone", provider_subject=body.phone)
    db.add(identity)

    await enqueue_outbox(db, "user.created", {"user_id": str(user.id), "phone": body.phone})
    await enqueue_outbox(db, "user.phone_verified", {"user_id": str(user.id), "phone": body.phone})

    user_agent = request.headers.get("User-Agent", "")[:512]
    return await _issue_token_pair(db, user, ip, user_agent)
