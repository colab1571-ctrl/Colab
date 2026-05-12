"""
auth-svc — Token refresh + logout endpoints.

POST /auth/token/refresh
POST /auth/logout
POST /auth/logout/all
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Session as DBSession
from app.schemas.auth import LogoutRequest, LogoutResponse, TokenPair, TokenRefreshRequest
from app.services import tokens
from colab_common.auth import AuthUser, require_user
from colab_common.db import get_session
from colab_common.errors import AuthError
from colab_common.events import enqueue_outbox
from colab_common.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/auth", tags=["token"])


@router.post("/token/refresh", response_model=TokenPair)
async def refresh_token(
    body: TokenRefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> TokenPair:
    """
    Rotate refresh token. Stolen-token detection: if JTI is replayed after
    rotation, the entire session chain is revoked.
    """
    ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(f"rl:refresh:ip:{ip}", capacity=60, refill_per_sec=1.0, retry_after=60)

    # Decode and validate refresh token
    claims = await tokens.decode_refresh_token(body.refresh_token)
    jti = claims.get("jti", "")
    session_id = claims.get("sid", "")
    user_id = claims.get("sub", "")

    # Replay detection — if already revoked, stolen token scenario
    if await tokens.is_jti_revoked(jti):
        # Revoke the entire session
        await tokens.mark_session_revoked(session_id)
        db_session = await db.scalar(select(DBSession).where(DBSession.id == uuid.UUID(session_id)))
        if db_session:
            db_session.revoked_at = datetime.now(UTC)
        raise AuthError("Token has already been used. Session revoked for security.")

    # Load session from DB
    refresh_hash = tokens.hash_token_str(body.refresh_token)
    db_session = await db.scalar(
        select(DBSession).where(
            DBSession.refresh_token_hash == refresh_hash,
            DBSession.revoked_at.is_(None),
        )
    )
    if db_session is None:
        raise AuthError("Session not found or revoked.")

    from app.models.user import User

    user = await db.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise AuthError("User not found or deactivated.")

    # Revoke old JTI
    from colab_common.settings import get_settings
    settings = get_settings()
    await tokens.mark_jti_revoked(jti, settings.jwt.refresh_ttl_seconds)

    # Mint new token pair
    new_refresh, new_jti = await tokens.mint_refresh_token(user_id, session_id)
    new_access = await tokens.mint_access_token(
        user_id,
        session_id,
        email_verified=user.email_verified_at is not None,
        identity_verified=False,
    )

    # Update session record
    db_session.refresh_token_hash = tokens.hash_token_str(new_refresh)
    db_session.refresh_jti = new_jti
    db_session.last_seen_at = datetime.now(UTC)

    return TokenPair(user_id=user.id, access_token=new_access, refresh_token=new_refresh)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    body: LogoutRequest,
    db: AsyncSession = Depends(get_session),
) -> LogoutResponse:
    """Revoke the provided refresh token's session."""
    try:
        claims = await tokens.decode_refresh_token(body.refresh_token)
        session_id = claims.get("sid", "")
        jti = claims.get("jti", "")
    except Exception:
        return LogoutResponse()  # Already invalid — silently succeed

    refresh_hash = tokens.hash_token_str(body.refresh_token)
    db_session = await db.scalar(
        select(DBSession).where(DBSession.refresh_token_hash == refresh_hash)
    )
    if db_session and not db_session.revoked_at:
        db_session.revoked_at = datetime.now(UTC)
        await tokens.mark_session_revoked(session_id)
        await tokens.mark_jti_revoked(jti, 2592000)

    return LogoutResponse()


@router.post("/logout/all", response_model=LogoutResponse)
async def logout_all(
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> LogoutResponse:
    """Revoke all sessions for the current user."""
    sessions = await db.scalars(
        select(DBSession).where(
            DBSession.user_id == uuid.UUID(user.user_id),
            DBSession.revoked_at.is_(None),
        )
    )
    now = datetime.now(UTC)
    for s in sessions:
        s.revoked_at = now
        await tokens.mark_session_revoked(str(s.id))

    await enqueue_outbox(db, "auth.session.revoked", {"user_id": user.user_id, "all": True})
    return LogoutResponse()
