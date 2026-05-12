"""
meeting-svc Pydantic schemas — request/response contracts.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Meeting
# ---------------------------------------------------------------------------


class MeetingCreateRequest(BaseModel):
    scheduled_at: datetime
    duration_min: int = Field(default=60, ge=15, le=480)
    bot_enabled: bool = False

    @field_validator("scheduled_at")
    @classmethod
    def must_be_future(cls, v: datetime) -> datetime:
        from datetime import UTC

        if v.tzinfo is None:
            raise ValueError("scheduled_at must include timezone info (UTC offset)")
        return v


class MeetingPatchRequest(BaseModel):
    scheduled_at: datetime | None = None
    duration_min: int | None = Field(default=None, ge=15, le=480)
    status: str | None = None

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str | None) -> str | None:
        if v is not None and v not in ("cancelled",):
            raise ValueError("Only 'cancelled' status transition is supported via PATCH")
        return v


class BotConsentStatus(BaseModel):
    participant_a: bool
    participant_b: bool


class MeetingOut(BaseModel):
    id: uuid.UUID
    collab_id: uuid.UUID
    organizer_profile_id: uuid.UUID
    scheduled_at: datetime
    duration_min: int
    join_url: str
    ics_url: str | None
    status: str
    bot_enabled: bool
    bot_status: str
    recall_bot_id: str | None
    bot_consent: BotConsentStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MeetingListResponse(BaseModel):
    items: list[MeetingOut]
    cursor: str | None
    has_more: bool


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


class ArtifactOut(BaseModel):
    id: uuid.UUID
    kind: str
    download_url: str
    ready_at: datetime

    model_config = {"from_attributes": True}


class ArtifactListResponse(BaseModel):
    items: list[ArtifactOut]


# ---------------------------------------------------------------------------
# Bot consent
# ---------------------------------------------------------------------------


class ConsentOut(BaseModel):
    profile_id: uuid.UUID
    consented_at: datetime
    both_consented: bool


class BotStartResponse(BaseModel):
    bot_status: str
    recall_bot_id: str | None
