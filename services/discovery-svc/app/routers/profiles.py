"""
discovery-svc — profile action router.

Endpoints:
  POST   /profile/{id}/hide-3mo
  DELETE /profile/{id}/hide-3mo
  POST   /profile/{id}/save
  DELETE /profile/{id}/save
  GET    /me/saved
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.schemas.feed import Hide3moResponse, SavedListResponse, ProfileCard, ErrorResponse
from app.services.cache import invalidate_user_feed, invalidate_recs
from app.services.feed import _fetch_profile_cards

router = APIRouter(tags=["profiles"])
logger = logging.getLogger(__name__)
_settings = get_settings()


async def _resolve_user_ids(request: Request) -> tuple[str, str]:
    user_id = request.headers.get("X-User-Id", "")
    profile_id = request.headers.get("X-Profile-Id", "")
    return user_id, profile_id


# ---------------------------------------------------------------------------
# Hide-3mo
# ---------------------------------------------------------------------------

@router.post(
    "/profile/{profile_id}/hide-3mo",
    response_model=Hide3moResponse,
    responses={409: {"model": ErrorResponse}},
)
async def hide_profile_3mo(
    profile_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(...),
) -> Hide3moResponse:
    user_id, _ = await _resolve_user_ids(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user context")

    now = datetime.now(tz=timezone.utc)
    hidden_until = now + timedelta(days=90)

    # Upsert — re-hide resets the timer
    await db.execute(
        sa_text("""
            INSERT INTO discovery.hide_3mo (user_id, hidden_profile_id, hidden_at, hidden_until)
            VALUES (:user_id, :profile_id, :now, :hidden_until)
            ON CONFLICT (user_id, hidden_profile_id) DO UPDATE
              SET hidden_at = EXCLUDED.hidden_at,
                  hidden_until = EXCLUDED.hidden_until
        """),
        {
            "user_id": user_id,
            "profile_id": str(profile_id),
            "now": now,
            "hidden_until": hidden_until,
        },
    )
    await db.commit()

    # Invalidate feed cache immediately — hidden profile must disappear
    await invalidate_user_feed(user_id)

    return Hide3moResponse(hidden_until=hidden_until)


@router.delete("/profile/{profile_id}/hide-3mo", status_code=status.HTTP_204_NO_CONTENT)
async def unhide_profile_3mo(
    profile_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(...),
) -> None:
    user_id, _ = await _resolve_user_ids(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user context")

    await db.execute(
        sa_text("""
            DELETE FROM discovery.hide_3mo
            WHERE user_id = :user_id AND hidden_profile_id = :profile_id
        """),
        {"user_id": user_id, "profile_id": str(profile_id)},
    )
    await db.commit()
    await invalidate_user_feed(user_id)


# ---------------------------------------------------------------------------
# Save profile
# ---------------------------------------------------------------------------

@router.post("/profile/{profile_id}/save", status_code=status.HTTP_201_CREATED)
async def save_profile(
    profile_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(...),
) -> dict:
    user_id, _ = await _resolve_user_ids(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user context")

    now = datetime.now(tz=timezone.utc)
    await db.execute(
        sa_text("""
            INSERT INTO discovery.saved_profiles (user_id, saved_profile_id, saved_at)
            VALUES (:user_id, :profile_id, :now)
            ON CONFLICT (user_id, saved_profile_id) DO NOTHING
        """),
        {"user_id": user_id, "profile_id": str(profile_id), "now": now},
    )
    await db.commit()

    return {"saved": True, "saved_at": now.isoformat()}


@router.delete("/profile/{profile_id}/save", status_code=status.HTTP_204_NO_CONTENT)
async def unsave_profile(
    profile_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(...),
) -> None:
    user_id, _ = await _resolve_user_ids(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user context")

    await db.execute(
        sa_text("""
            DELETE FROM discovery.saved_profiles
            WHERE user_id = :user_id AND saved_profile_id = :profile_id
        """),
        {"user_id": user_id, "profile_id": str(profile_id)},
    )
    await db.commit()


@router.get("/me/saved", response_model=SavedListResponse)
async def get_saved_profiles(
    request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(...),
) -> SavedListResponse:
    user_id, _ = await _resolve_user_ids(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user context")

    result = await db.execute(
        sa_text("""
            SELECT saved_profile_id::text
            FROM discovery.saved_profiles
            WHERE user_id = :user_id
            ORDER BY saved_at DESC
        """),
        {"user_id": user_id},
    )
    rows = result.fetchall()
    profile_ids = [str(r[0]) for r in rows]

    cards = await _fetch_profile_cards(profile_ids, user_id, authorization, set(profile_ids))

    return SavedListResponse(profiles=cards, total=len(cards))
