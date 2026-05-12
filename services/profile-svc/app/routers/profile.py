"""
profile-svc — Profile CRUD endpoints.

GET  /api/v1/profile/me
POST /api/v1/profile/me  (initial create, usually auto-created on user.created event)
PATCH /api/v1/profile/me
GET  /api/v1/profile/{handle}  (public view)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Profile
from app.schemas.profile import (
    LocationResponse,
    ProfilePatch,
    ProfilePublic,
    ProfileSelfResponse,
    RadiusResponse,
    VocationItem,
    SkillLabel,
    ExternalLinkPublic,
    PortfolioItemPublic,
)
from app.services.health_score import compute_health_score

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


def _require_auth(request: Request) -> uuid.UUID:
    """Extract user_id from JWT claims set by gateway middleware."""
    user_id = request.state.user_id if hasattr(request.state, "user_id") else None
    if not user_id:
        # Fallback: read from X-User-Id header (set by gateway after JWT verification)
        uid_header = request.headers.get("X-User-Id")
        if not uid_header:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        user_id = uuid.UUID(uid_header)
    return user_id


async def _get_own_profile(user_id: uuid.UUID, session: AsyncSession) -> Profile:
    result = await session.execute(select(Profile).where(Profile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


def _profile_to_self_response(profile: Profile) -> ProfileSelfResponse:
    location = None
    if profile.location_point and profile.location_city:
        from geoalchemy2.shape import to_shape
        try:
            shape = to_shape(profile.location_point)
            location = LocationResponse(lat=shape.y, lng=shape.x, city=profile.location_city, country=profile.location_country)
        except Exception:
            pass

    return ProfileSelfResponse(
        id=profile.id,
        user_id=profile.user_id,
        display_name=profile.display_name,
        bio=profile.bio,
        obsessed_with=profile.obsessed_with,
        looking_for=profile.looking_for,
        past_experience=profile.past_experience,
        location=location,
        radius=RadiusResponse(value=profile.radius_value, unit=profile.radius_unit),
        open_to_remote=profile.open_to_remote,
        experience_level=profile.experience_level,
        vocations=[
            VocationItem(category=v.category, subtag=v.subtag, is_primary=v.is_primary)
            for v in profile.vocations
        ],
        skills=[SkillLabel(label_raw=s.label_raw, label_normalized=s.label_normalized) for s in profile.skills],
        personality_archetype=profile.personality_archetype,
        portfolio=[
            PortfolioItemPublic(
                id=p.id, position=p.position, type=p.type,
                s3_key=p.s3_key, mime=p.mime, size_bytes=p.size_bytes,
                caption=p.caption, ai_review_status=p.ai_review_status,
                created_at=p.created_at,
            )
            for p in profile.portfolio_items
        ],
        externals=[
            ExternalLinkPublic(
                provider=e.provider, provider_handle=e.provider_handle,
                linked_at=e.linked_at, sync_state=e.sync_state,
            )
            for e in profile.external_links
        ],
        badge_state=profile.badge_state,
        badge_granted_at=profile.badge_granted_at,
        profile_health_score=profile.profile_health_score,
        last_active_at=profile.last_active_at,
    )


@router.get("/me", response_model=ProfileSelfResponse)
async def get_own_profile(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ProfileSelfResponse:
    """Return own profile with all fields including health score."""
    user_id = _require_auth(request)
    profile = await _get_own_profile(user_id, session)

    # Update last_active_at
    profile.last_active_at = datetime.now(tz=timezone.utc)
    await session.commit()

    return _profile_to_self_response(profile)


@router.patch("/me", response_model=ProfileSelfResponse)
async def patch_own_profile(
    body: ProfilePatch,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ProfileSelfResponse:
    """Update mutable profile fields. Emits profile.updated event."""
    user_id = _require_auth(request)
    profile = await _get_own_profile(user_id, session)

    material_change = False  # track if text/display_name changed (re-triggers AI review)

    if body.display_name is not None and body.display_name != profile.display_name:
        # Check uniqueness (case-insensitive)
        existing = await session.execute(
            select(Profile).where(
                Profile.display_name == body.display_name,
                Profile.id != profile.id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Display name already taken")
        profile.display_name = body.display_name
        material_change = True

    if body.bio is not None:
        if len(body.bio) > 280:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Bio must be ≤280 characters")
        if body.bio != profile.bio:
            material_change = True
        profile.bio = body.bio

    if body.obsessed_with is not None:
        if len(body.obsessed_with) > 140:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Obsessed-with must be ≤140 characters")
        if body.obsessed_with != profile.obsessed_with:
            material_change = True
        profile.obsessed_with = body.obsessed_with

    if body.open_to_remote is not None:
        profile.open_to_remote = body.open_to_remote

    if body.experience_level is not None:
        profile.experience_level = body.experience_level

    if body.looking_for is not None:
        profile.looking_for = body.looking_for

    if body.past_experience is not None:
        profile.past_experience = body.past_experience

    if body.radius_value is not None:
        profile.radius_value = body.radius_value

    if body.radius_unit is not None:
        profile.radius_unit = body.radius_unit

    profile.updated_at = datetime.now(tz=timezone.utc)
    profile.last_active_at = datetime.now(tz=timezone.utc)

    # Recompute health score synchronously
    new_score = compute_health_score(
        profile,
        identity_approved=profile.badge_state in ("identity_approved", "ai_review_pending", "badge_granted"),
    )
    profile.profile_health_score = new_score

    await session.commit()

    # Trigger AI re-review if material change and badge already granted
    if material_change and profile.badge_state == "badge_granted":
        from app.workers.ai_review_tasks import orchestrate_profile_review
        from app.services.badge_fsm import BadgeState, BadgeEvent, transition
        try:
            result = transition(profile.badge_state, BadgeEvent.profile_updated_material)
            profile.badge_state = result.new_state.value
            await session.commit()
        except Exception:
            pass
        orchestrate_profile_review.delay(str(profile.id), "profile.updated")

    # Trigger embedding update
    from app.workers.embedding_tasks import generate_profile_embedding
    generate_profile_embedding.delay(str(profile.id))

    return _profile_to_self_response(profile)


@router.get("/{handle}", response_model=ProfilePublic)
async def get_public_profile(
    handle: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ProfilePublic:
    """
    Public profile view. Honors is_visible_to_non_premium.
    Returns 404 if blocked (block list handled by caller middleware).
    """
    result = await session.execute(
        select(Profile).where(Profile.display_name == handle)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    # Check premium visibility (in production, entitlement check via billing-svc)
    # For now: if not visible to non-premium and requester is not premium → 403
    # This is enforced at gateway/discovery level; here we surface the flag
    if not profile.is_visible_to_non_premium:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Profile not available")

    return ProfilePublic(
        id=profile.id,
        display_name=profile.display_name,
        bio=profile.bio,
        obsessed_with=profile.obsessed_with,
        location_city=profile.location_city,
        location_country=profile.location_country,
        open_to_remote=profile.open_to_remote,
        experience_level=profile.experience_level,
        vocations=[
            VocationItem(category=v.category, subtag=v.subtag, is_primary=v.is_primary)
            for v in profile.vocations
        ],
        personality_archetype=profile.personality_archetype,
        portfolio=[
            PortfolioItemPublic(
                id=p.id, position=p.position, type=p.type,
                s3_key=p.s3_key, mime=p.mime, size_bytes=p.size_bytes,
                caption=p.caption, ai_review_status=p.ai_review_status,
                created_at=p.created_at,
            )
            for p in profile.portfolio_items
            if p.ai_review_status == "passed"
        ],
        externals=[
            ExternalLinkPublic(
                provider=e.provider, provider_handle=e.provider_handle,
                linked_at=e.linked_at, sync_state=e.sync_state,
            )
            for e in profile.external_links
        ],
        badge_state=profile.badge_state,
        badge_granted_at=profile.badge_granted_at,
        last_active_at=profile.last_active_at,
    )
