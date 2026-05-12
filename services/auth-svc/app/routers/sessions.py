"""
auth-svc — Session management endpoints.

GET  /auth/sessions
DELETE /auth/sessions/{id}
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Session as DBSession
from app.schemas.auth import SessionListResponse, SessionOut
from app.services.tokens import mark_session_revoked
from colab_common.auth import AuthUser, require_user
from colab_common.db import get_session
from colab_common.errors import ForbiddenError, NotFoundError
from colab_common.events import enqueue_outbox

router = APIRouter(prefix="/auth", tags=["sessions"])


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> SessionListResponse:
    """List all active sessions for the current user."""
    rows = await db.scalars(
        select(DBSession).where(
            DBSession.user_id == uuid.UUID(user.user_id),
            DBSession.revoked_at.is_(None),
        )
    )
    current_sid = user.raw_claims.get("sid", "")
    session_list = []
    for s in rows:
        out = SessionOut(
            id=s.id,
            user_agent=s.user_agent,
            ip=s.ip,
            last_seen_at=s.last_seen_at,
            created_at=s.created_at,
            is_current=str(s.id) == current_sid,
        )
        session_list.append(out)
    return SessionListResponse(sessions=session_list)


@router.delete("/sessions/{session_id}", response_model=SessionListResponse)
async def revoke_session(
    session_id: uuid.UUID,
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> SessionListResponse:
    """Revoke a specific session. User may only revoke their own sessions."""
    db_session = await db.get(DBSession, session_id)
    if db_session is None:
        raise NotFoundError("Session")
    if str(db_session.user_id) != user.user_id:
        raise ForbiddenError("You cannot revoke another user's session.")

    db_session.revoked_at = datetime.now(UTC)
    await mark_session_revoked(str(session_id))
    await enqueue_outbox(
        db,
        "auth.session.revoked",
        {"user_id": user.user_id, "session_id": str(session_id)},
    )

    return await list_sessions(user=user, db=db)
