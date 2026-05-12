"""
discovery-svc — feed router.

Endpoints:
  GET  /feed
  POST /feed/preference/mode
  GET  /feed/picked-for-you
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import get_db, AsyncSession
from app.schemas.feed import (
    FeedFilters,
    FeedResponse,
    ModePreferenceRequest,
    ModePreferenceResponse,
    PickedForYouResponse,
    ProfileCard,
    encode_cursor,
    FeedCursor,
    ErrorResponse,
)
from app.services.cache import get_feed_mode, set_feed_mode, get_recs
from app.services.feed import build_feed, get_entitlement_tier, _fetch_profile_cards

router = APIRouter(tags=["feed"])
logger = logging.getLogger(__name__)
_settings = get_settings()
_http = httpx.AsyncClient(timeout=5.0)


def _get_user_id(authorization: str = Header(...)) -> str:
    """Extract user_id from Authorization header (JWT sub claim, stub)."""
    # In production this is decoded by API Gateway / colab_common JWT middleware
    # For now return header value — gateway injects X-User-Id
    return authorization  # placeholder; real impl uses colab_common.auth.decode_jwt


def _get_jwt(authorization: str = Header(...)) -> str:
    return authorization


async def _resolve_user_ids(request: Request) -> tuple[str, str]:
    """Returns (user_id, profile_id) from request headers set by API Gateway."""
    user_id = request.headers.get("X-User-Id", "")
    profile_id = request.headers.get("X-Profile-Id", "")
    return user_id, profile_id


@router.get("/feed", response_model=FeedResponse, responses={402: {"model": ErrorResponse}})
async def get_feed(
    request: Request,
    mode: str = Query("scroll", pattern="^(scroll|swipe)$"),
    cursor: str | None = Query(None),
    page_size: int = Query(20, ge=1, le=50),
    filters: str | None = Query(None, description="URI-encoded JSON filter object"),
    authorization: str = Header(...),
) -> JSONResponse:
    user_id, profile_id = await _resolve_user_ids(request)
    if not user_id or not profile_id:
        raise HTTPException(status_code=401, detail="Missing user context headers")

    # Parse filters
    parsed_filters = FeedFilters()
    if filters:
        try:
            raw = json.loads(urllib.parse.unquote(filters))
            parsed_filters = FeedFilters(**raw)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid_filter")

    # Resolve mode: prefer query param, else cached preference, else default
    cached_mode = await get_feed_mode(user_id)
    effective_mode = mode or cached_mode or "scroll"

    feed_resp, http_status = await build_feed(
        viewer_user_id=user_id,
        viewer_profile_id=profile_id,
        jwt=authorization,
        mode=effective_mode,
        cursor_token=cursor,
        page_size=page_size,
        filters=parsed_filters,
    )

    if http_status == 402:
        from datetime import timezone as tz
        resets_at = (
            datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=1)
        )
        return JSONResponse(
            status_code=402,
            content={
                "error": "daily_cap_reached",
                "cap": _settings.rate_limit_feed_profiles_free_per_day,
                "resets_at": resets_at.isoformat(),
            },
        )

    return JSONResponse(
        status_code=200,
        content=feed_resp.model_dump(mode="json"),
    )


@router.post("/feed/preference/mode", response_model=ModePreferenceResponse)
async def set_mode_preference(
    request: Request,
    body: ModePreferenceRequest,
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(...),
) -> ModePreferenceResponse:
    user_id, _ = await _resolve_user_ids(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user context")

    # Write to Redis
    await set_feed_mode(user_id, body.mode)

    # Upsert to DB
    from sqlalchemy import text as sa_text
    now = datetime.now(tz=timezone.utc)
    await db.execute(
        sa_text("""
            INSERT INTO discovery.feed_preferences (user_id, mode, updated_at)
            VALUES (:user_id, :mode, :now)
            ON CONFLICT (user_id) DO UPDATE
              SET mode = EXCLUDED.mode, updated_at = EXCLUDED.updated_at
        """),
        {"user_id": user_id, "mode": body.mode, "now": now},
    )
    await db.commit()

    return ModePreferenceResponse(mode=body.mode, updated_at=now)


@router.get("/feed/picked-for-you", response_model=PickedForYouResponse)
async def get_picked_for_you(
    request: Request,
    authorization: str = Header(...),
) -> PickedForYouResponse:
    user_id, profile_id = await _resolve_user_ids(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user context")

    # Try Redis recs cache first
    profile_ids = await get_recs(user_id)
    generated_at = datetime.now(tz=timezone.utc)

    if profile_ids is None:
        # Cold-start: fetch real-time from matching-svc
        try:
            resp = await _http.get(
                f"{_settings.matching_svc_url}/internal/recommendations/{profile_id}",
                headers={"X-Internal-Service-Token": _settings.internal_service_secret},
            )
            resp.raise_for_status()
            data = resp.json()
            profile_ids = data.get("profile_ids", [])
            generated_at = datetime.fromisoformat(
                data.get("generated_at", generated_at.isoformat())
            )
        except Exception as exc:
            logger.warning("matching-svc recs fetch failed: %s", exc)
            profile_ids = []

    cards = await _fetch_profile_cards(profile_ids, user_id, authorization, set())

    next_refresh_at = (
        datetime.now(tz=timezone.utc).replace(hour=3, minute=0, second=0, microsecond=0)
        + timedelta(days=1)
    )

    return PickedForYouResponse(
        profiles=cards,
        generated_at=generated_at,
        next_refresh_at=next_refresh_at,
    )
