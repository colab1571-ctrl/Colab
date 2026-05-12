"""
discovery-svc — request/response Pydantic schemas.

IMPORTANT: profile_health_score is NEVER included in any response schema
per master §0 and plan §3.2. CI lint rule enforces absence of health_score
in OpenAPI output.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Filter schema
# ---------------------------------------------------------------------------

class FeedFilters(BaseModel):
    vocation_categories: list[str] = Field(default_factory=list)
    radius_km: float | None = None
    anywhere: bool = False
    experience_level_min: int | None = Field(None, ge=1, le=5)
    experience_level_max: int | None = Field(None, ge=1, le=5)
    open_to_remote: bool | None = None
    last_active_days: int = Field(90, ge=1, le=365)
    min_successful_collabs: int = Field(0, ge=0)

    @model_validator(mode="after")
    def validate_exp_levels(self) -> "FeedFilters":
        if (
            self.experience_level_min is not None
            and self.experience_level_max is not None
            and self.experience_level_min > self.experience_level_max
        ):
            raise ValueError("experience_level_min must be <= experience_level_max")
        return self

    def filter_hash(self) -> str:
        return hashlib.sha256(
            self.model_dump_json(exclude_none=False).encode()
        ).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------

class FeedCursor(BaseModel):
    fh: str  # filter_hash 8 chars
    o: int   # offset
    d: str   # YYYY-MM-DD


def encode_cursor(cursor: FeedCursor) -> str:
    raw = json.dumps(cursor.model_dump(), separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(token: str) -> FeedCursor | None:
    try:
        padded = token + "=" * (4 - len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        data = json.loads(raw)
        return FeedCursor(**data)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Profile card — never includes health_score
# ---------------------------------------------------------------------------

class VocationCard(BaseModel):
    category: str
    subtag: str


class PortfolioPreviewItem(BaseModel):
    type: str
    url: str
    caption: str | None = None


class ProfileCard(BaseModel):
    id: UUID
    display_name: str | None
    location_city: str | None
    badge_state: str
    vocations: list[VocationCard]
    bio: str | None
    obsessed_with: str | None
    experience_level: int | None
    open_to_remote: bool
    portfolio_preview: list[PortfolioPreviewItem]
    collab_count: int
    last_active_relative: str | None
    saved: bool
    # match_score intentionally null — never surfaced to clients
    match_score: None = None

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Feed response
# ---------------------------------------------------------------------------

class FeedResponse(BaseModel):
    mode: str
    profiles: list[ProfileCard]
    next_cursor: str | None
    remaining_today: int | None = None  # omitted for Premium
    cap: int | None = None


class DailyCapReachedError(BaseModel):
    error: str = "daily_cap_reached"
    cap: int
    resets_at: datetime


# ---------------------------------------------------------------------------
# Mode preference
# ---------------------------------------------------------------------------

class ModePreferenceRequest(BaseModel):
    mode: str = Field(..., pattern="^(scroll|swipe)$")


class ModePreferenceResponse(BaseModel):
    mode: str
    updated_at: datetime


# ---------------------------------------------------------------------------
# Hide-3mo
# ---------------------------------------------------------------------------

class Hide3moResponse(BaseModel):
    hidden_until: datetime


# ---------------------------------------------------------------------------
# Save profile
# ---------------------------------------------------------------------------

class SavedListResponse(BaseModel):
    profiles: list[ProfileCard]
    total: int


# ---------------------------------------------------------------------------
# Picked-for-you
# ---------------------------------------------------------------------------

class PickedForYouResponse(BaseModel):
    profiles: list[ProfileCard]
    generated_at: datetime
    next_refresh_at: datetime


# ---------------------------------------------------------------------------
# Generic error
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    error: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
