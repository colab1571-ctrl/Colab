"""
Notifications API router.

Endpoints:
  GET  /notifications
  POST /notifications/{id}/read
  POST /notifications/read-all
  POST /notifications/unsubscribe  (RFC 8058 one-click)
"""

from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timezone
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from colab_common.auth import AuthUser, require_user
from colab_common.db import get_session

from ..models import Notification, NotificationPreference
from ..schemas import (
    NotificationListResponse,
    NotificationOut,
    NotificationReadResponse,
    ReadAllResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["notifications"])

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"


# ---------------------------------------------------------------------------
# GET /notifications
# ---------------------------------------------------------------------------


@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    cursor: str | None = Query(default=None),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=50),
    auth_user: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> NotificationListResponse:
    user_id = auth_user.user_id
    stmt = select(Notification).where(Notification.user_id == user_id)  # type: ignore[arg-type]

    if unread_only:
        stmt = stmt.where(Notification.in_app_seen_at.is_(None))

    # Cursor-based pagination: decode cursor to (created_at, id)
    if cursor:
        try:
            decoded = json.loads(base64.b64decode(cursor).decode())
            pivot_created_at = decoded["created_at"]
            pivot_id = decoded["id"]
            stmt = stmt.where(
                (Notification.created_at < pivot_created_at)
                | ((Notification.created_at == pivot_created_at) & (Notification.id < pivot_id))  # type: ignore[arg-type]
            )
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid cursor")

    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
    stmt = stmt.limit(limit + 1)

    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    has_more = len(rows) > limit
    items = rows[:limit]

    next_cursor: str | None = None
    if has_more and items:
        last = items[-1]
        next_cursor = base64.b64encode(
            json.dumps({"created_at": last.created_at.isoformat(), "id": str(last.id)}).encode()
        ).decode()

    return NotificationListResponse(
        items=[NotificationOut.model_validate(n) for n in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


# ---------------------------------------------------------------------------
# POST /notifications/{id}/read
# ---------------------------------------------------------------------------


@router.post("/notifications/{notif_id}/read", response_model=NotificationReadResponse)
async def mark_read(
    notif_id: UUID,
    auth_user: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> NotificationReadResponse:
    user_id = auth_user.user_id
    stmt = select(Notification).where(
        Notification.id == notif_id,
        Notification.user_id == user_id,  # type: ignore[arg-type]
    )
    result = await session.execute(stmt)
    notif = result.scalar_one_or_none()

    if notif is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    now = datetime.now(tz=timezone.utc)
    if notif.in_app_seen_at is None:
        await session.execute(
            update(Notification)
            .where(Notification.id == notif_id)
            .values(in_app_seen_at=now)
        )
    else:
        now = notif.in_app_seen_at

    return NotificationReadResponse(id=notif_id, in_app_seen_at=now)


# ---------------------------------------------------------------------------
# POST /notifications/read-all
# ---------------------------------------------------------------------------


@router.post("/notifications/read-all", response_model=ReadAllResponse)
async def mark_all_read(
    auth_user: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> ReadAllResponse:
    user_id = auth_user.user_id
    now = datetime.now(tz=timezone.utc)
    result = await session.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,  # type: ignore[arg-type]
            Notification.in_app_seen_at.is_(None),
        )
        .values(in_app_seen_at=now)
        .returning(Notification.id)
    )
    updated_ids = result.fetchall()
    return ReadAllResponse(updated_count=len(updated_ids))


# ---------------------------------------------------------------------------
# POST /notifications/unsubscribe (RFC 8058 one-click)
# ---------------------------------------------------------------------------


@router.post("/notifications/unsubscribe")
async def one_click_unsubscribe(
    token: str = Query(...),
    list_unsubscribe: str = Form(default=""),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """
    Handles RFC 8058 List-Unsubscribe-Post.
    Token encodes {user_id, type, channel=email}.
    No auth required — the signed token IS the auth.
    """
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = claims["user_id"]
        notif_type = claims["type"]
        channel = claims.get("channel", "email")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid unsubscribe token")

    # Upsert preference: set enabled=False
    stmt = select(NotificationPreference).where(
        NotificationPreference.user_id == user_id,  # type: ignore[arg-type]
        NotificationPreference.type == notif_type,  # type: ignore[arg-type]
        NotificationPreference.channel == channel,  # type: ignore[arg-type]
    )
    result = await session.execute(stmt)
    pref = result.scalar_one_or_none()

    if pref is not None:
        await session.execute(
            update(NotificationPreference)
            .where(
                NotificationPreference.user_id == user_id,  # type: ignore[arg-type]
                NotificationPreference.type == notif_type,  # type: ignore[arg-type]
                NotificationPreference.channel == channel,  # type: ignore[arg-type]
            )
            .values(enabled=False)
        )
    else:
        pref = NotificationPreference(
            user_id=user_id,  # type: ignore[arg-type]
            type=notif_type,  # type: ignore[arg-type]
            channel=channel,  # type: ignore[arg-type]
            enabled=False,
        )
        session.add(pref)

    logger.info("One-click unsubscribe: user=%s type=%s channel=%s", user_id, notif_type, channel)
    return {"status": "Unsubscribed"}
