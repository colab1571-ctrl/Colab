"""
profile-svc — Badge endpoints.

GET  /api/v1/profile/me/badge
POST /api/v1/profile/me/badge/recheck  (rate-limited 1/24h)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import Profile
from app.models.profile import PortfolioItem, ProfileReview
from app.schemas.profile import AIReviewSummary, BadgeRecheckResponse, BadgeResponse
from app.services.badge_fsm import BadgeEvent, BadgeState, next_action, transition

router = APIRouter(prefix="/api/v1/profile/me/badge", tags=["badge"])


def _require_auth(request: Request) -> uuid.UUID:
    uid_header = request.headers.get("X-User-Id")
    if not uid_header:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return uuid.UUID(uid_header)


async def _get_profile(user_id: uuid.UUID, session: AsyncSession) -> Profile:
    result = await session.execute(select(Profile).where(Profile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


def _get_redis():
    return aioredis.from_url(get_settings().redis_url, decode_responses=True)


@router.get("", response_model=BadgeResponse)
async def get_badge(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> BadgeResponse:
    """Return badge state, held reason, next action, and AI review summary."""
    user_id = _require_auth(request)
    profile = await _get_profile(user_id, session)
    settings = get_settings()

    # Get latest AI review score
    review_result = await session.execute(
        select(ProfileReview)
        .where(ProfileReview.profile_id == profile.id)
        .order_by(ProfileReview.created_at.desc())
        .limit(1)
    )
    latest_review = review_result.scalar_one_or_none()

    # Count hidden portfolio items
    hidden_result = await session.execute(
        select(PortfolioItem)
        .where(
            PortfolioItem.profile_id == profile.id,
            PortfolioItem.ai_review_status == "hidden",
        )
    )
    hidden_count = len(hidden_result.scalars().all())

    return BadgeResponse(
        state=profile.badge_state,
        granted_at=profile.badge_granted_at,
        held_reason=profile.badge_held_reason,
        next_action=next_action(profile.badge_state),
        ai_review_summary=AIReviewSummary(
            latest_score=latest_review.score if latest_review else None,
            hidden_items=hidden_count,
        ),
    )


@router.post("/recheck", response_model=BadgeRecheckResponse)
async def recheck_badge(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> BadgeRecheckResponse:
    """
    Request AI re-review. Rate-limited to 1 per 24h per user via Redis.
    """
    user_id = _require_auth(request)
    profile = await _get_profile(user_id, session)
    settings = get_settings()

    # Rate limit check
    redis = _get_redis()
    rate_key = f"badge:recheck:{profile.id}"
    try:
        last_recheck = await redis.get(rate_key)
        if last_recheck:
            last_ts = datetime.fromisoformat(last_recheck)
            cooldown = timedelta(hours=settings.badge_recheck_cooldown_hours)
            earliest_next = last_ts + cooldown
            if datetime.now(tz=timezone.utc) < earliest_next:
                return BadgeRecheckResponse(queued=False, earliest_next_recheck_at=earliest_next)

        # Check FSM allows recheck
        try:
            result = transition(profile.badge_state, BadgeEvent.badge_recheck_requested)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Badge recheck not available in state {profile.badge_state!r}",
            )

        profile.badge_state = result.new_state.value
        await session.commit()

        # Record recheck timestamp
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        await redis.setex(rate_key, settings.badge_recheck_cooldown_hours * 3600, now_iso)

        # Fire AI review
        from app.workers.ai_review_tasks import orchestrate_profile_review
        orchestrate_profile_review.delay(str(profile.id), "badge.recheck")

    finally:
        await redis.aclose()

    return BadgeRecheckResponse(queued=True, earliest_next_recheck_at=None)
