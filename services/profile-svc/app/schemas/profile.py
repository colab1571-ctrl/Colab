"""
profile-svc — Pydantic request/response schemas.

All API contracts per plan §9.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

class LocationResponse(BaseModel):
    lat: float
    lng: float
    city: str | None = None
    country: str | None = None


class RadiusResponse(BaseModel):
    value: int
    unit: Literal["mi", "km"]


# ---------------------------------------------------------------------------
# Vocation / Skill
# ---------------------------------------------------------------------------

class VocationItem(BaseModel):
    category: str = Field(..., min_length=1, max_length=64)
    subtag: str = Field(..., min_length=1, max_length=128)
    is_primary: bool = False


class VocationsPut(BaseModel):
    vocations: list[VocationItem] = Field(..., min_length=1)


class SkillLabel(BaseModel):
    label_raw: str
    label_normalized: str | None = None


class SkillsPut(BaseModel):
    labels: list[str] = Field(..., max_length=20)


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

class PortfolioUploadRequest(BaseModel):
    type: Literal["image", "audio", "video"]
    mime: str
    size_bytes: int = Field(..., gt=0)


class PortfolioUploadResponse(BaseModel):
    upload: dict[str, Any]  # presigned POST fields
    portfolio_item_id: uuid.UUID
    expires_at: datetime


class PortfolioFinalizeRequest(BaseModel):
    caption: str | None = Field(None, max_length=200)
    position: int | None = Field(None, ge=0, le=11)


class PortfolioItemPublic(BaseModel):
    id: uuid.UUID
    position: int
    type: str
    s3_key: str
    mime: str
    size_bytes: int
    caption: str | None = None
    ai_review_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# External links
# ---------------------------------------------------------------------------

class ExternalLinkPublic(BaseModel):
    provider: str
    provider_handle: str | None = None
    linked_at: datetime
    sync_state: str

    model_config = {"from_attributes": True}


class OAuthConnectResponse(BaseModel):
    authorize_url: str
    state: str


# ---------------------------------------------------------------------------
# Personality quiz
# ---------------------------------------------------------------------------

class PersonalityAnswerItem(BaseModel):
    question_key: str
    answer_key: str


class PersonalitySubmit(BaseModel):
    answers: list[PersonalityAnswerItem] = Field(..., min_length=5, max_length=7)


class PersonalityResult(BaseModel):
    archetype: str
    scores: dict[str, float]


# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------

class ProfileCreate(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=40)
    bio: str | None = Field(None, max_length=280)
    obsessed_with: str | None = Field(None, max_length=140)
    open_to_remote: bool = False
    experience_level: int | None = Field(None, ge=1, le=5)
    looking_for: str | None = Field(None, max_length=500)
    past_experience: str | None = Field(None, max_length=1000)


class ProfilePatch(BaseModel):
    display_name: str | None = Field(None, min_length=2, max_length=40)
    bio: str | None = Field(None, max_length=280)
    obsessed_with: str | None = Field(None, max_length=140)
    open_to_remote: bool | None = None
    experience_level: int | None = Field(None, ge=1, le=5)
    looking_for: str | None = Field(None, max_length=500)
    past_experience: str | None = Field(None, max_length=1000)
    radius_value: int | None = Field(None, ge=1, le=9999)
    radius_unit: Literal["mi", "km"] | None = None


class ProfileSelfResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str | None = None
    bio: str | None = None
    obsessed_with: str | None = None
    looking_for: str | None = None
    past_experience: str | None = None
    location: LocationResponse | None = None
    radius: RadiusResponse
    open_to_remote: bool
    experience_level: int | None = None
    vocations: list[VocationItem] = []
    skills: list[SkillLabel] = []
    personality_archetype: str | None = None
    portfolio: list[PortfolioItemPublic] = []
    externals: list[ExternalLinkPublic] = []
    badge_state: str
    badge_granted_at: datetime | None = None
    profile_health_score: float
    last_active_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProfilePublic(BaseModel):
    """Public profile view — PII limited to city + country, no lat/lng."""
    id: uuid.UUID
    display_name: str | None = None
    bio: str | None = None
    obsessed_with: str | None = None
    location_city: str | None = None
    location_country: str | None = None
    open_to_remote: bool
    experience_level: int | None = None
    vocations: list[VocationItem] = []
    personality_archetype: str | None = None
    portfolio: list[PortfolioItemPublic] = []
    externals: list[ExternalLinkPublic] = []
    badge_state: str
    badge_granted_at: datetime | None = None
    last_active_at: datetime | None = None

    model_config = {"from_attributes": True}


class ReorderRequest(BaseModel):
    order: list[uuid.UUID]  # item IDs in desired position order


# ---------------------------------------------------------------------------
# Badge
# ---------------------------------------------------------------------------

class AIReviewSummary(BaseModel):
    latest_score: float | None = None
    hidden_items: int = 0


class BadgeResponse(BaseModel):
    state: str
    granted_at: datetime | None = None
    held_reason: str | None = None
    next_action: str | None = None
    ai_review_summary: AIReviewSummary


class BadgeRecheckResponse(BaseModel):
    queued: bool
    earliest_next_recheck_at: datetime | None = None


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

class ProfileEmbeddingResponse(BaseModel):
    profile_id: uuid.UUID
    embedding: list[float] | None = None
    dimensions: int | None = None


class ProfileSummaryInternal(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    badge_state: str
    profile_health_score: float
    display_name: str | None = None
