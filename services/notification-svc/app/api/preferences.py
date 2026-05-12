"""
Notification preferences API router.

Endpoints:
  GET   /notifications/preferences
  PATCH /notifications/preferences
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from colab_common.auth import AuthUser, require_user
from colab_common.db import get_session

from ..models import NotificationChannel, NotificationPreference, NotificationType
from ..schemas import (
    PatchPreferencesRequest,
    PatchPreferencesResponse,
    PreferenceOut,
    PreferencesResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["preferences"])

VALID_TYPES = {t.value for t in NotificationType}
VALID_CHANNELS = {c.value for c in NotificationChannel}


@router.get("/notifications/preferences", response_model=PreferencesResponse)
async def get_preferences(
    auth_user: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> PreferencesResponse:
    user_id = auth_user.user_id
    stmt = select(NotificationPreference).where(
        NotificationPreference.user_id == user_id  # type: ignore[arg-type]
    )
    result = await session.execute(stmt)
    prefs = list(result.scalars().all())
    return PreferencesResponse(preferences=[PreferenceOut.model_validate(p) for p in prefs])


@router.patch("/notifications/preferences", response_model=PatchPreferencesResponse)
async def patch_preferences(
    body: PatchPreferencesRequest,
    auth_user: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> PatchPreferencesResponse:
    # Validate all updates first
    for upd in body.updates:
        if upd.type not in VALID_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid notification type: {upd.type}")
        if upd.channel not in VALID_CHANNELS:
            raise HTTPException(status_code=400, detail=f"Invalid channel: {upd.channel}")

    user_id = auth_user.user_id
    updated: list[PreferenceOut] = []

    for upd in body.updates:
        stmt = select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,  # type: ignore[arg-type]
            NotificationPreference.type == upd.type,  # type: ignore[arg-type]
            NotificationPreference.channel == upd.channel,  # type: ignore[arg-type]
        )
        result = await session.execute(stmt)
        pref = result.scalar_one_or_none()

        if pref is None:
            pref = NotificationPreference(
                user_id=user_id,  # type: ignore[arg-type]
                type=upd.type,  # type: ignore[arg-type]
                channel=upd.channel,  # type: ignore[arg-type]
                enabled=upd.enabled,
            )
            session.add(pref)
            await session.flush()
        else:
            await session.execute(
                update(NotificationPreference)
                .where(
                    NotificationPreference.user_id == user_id,  # type: ignore[arg-type]
                    NotificationPreference.type == upd.type,  # type: ignore[arg-type]
                    NotificationPreference.channel == upd.channel,  # type: ignore[arg-type]
                )
                .values(enabled=upd.enabled)
                .returning(NotificationPreference)
            )
            await session.refresh(pref)

        updated.append(PreferenceOut.model_validate(pref))

    return PatchPreferencesResponse(updated=updated)
