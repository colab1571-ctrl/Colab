"""collab-svc Pydantic schemas (request/response)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums (as string literals for Pydantic)
# ---------------------------------------------------------------------------

CollabStatus = Literal["still_deciding", "in_progress", "completed", "didnt_work_out"]
FeedbackRating = Literal["up", "down"]
FeedbackTarget = Literal["project", "partner"]
ExportStatus = Literal["pending", "generating", "ready", "failed"]

FEEDBACK_TAGS = frozenset(
    [
        "communicative",
        "responsive",
        "professional",
        "creative",
        "reliable",
        "flexible",
        "ghosted",
        "slow_to_respond",
        "missed_deadlines",
        "scope_creep",
        "great_outcome",
        "met_goals",
        "learned_a_lot",
        "good_creative_fit",
        "incomplete",
        "unclear_direction",
        "changed_scope",
        "technical_issues",
    ]
)


# ---------------------------------------------------------------------------
# Shared sub-schemas
# ---------------------------------------------------------------------------


class ParticipantStub(BaseModel):
    profile_id: uuid.UUID
    display_name: str
    avatar_url: str | None = None


class StatusEventOut(BaseModel):
    id: uuid.UUID
    prev_status: str
    new_status: str
    actor_profile_id: uuid.UUID
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackOut(BaseModel):
    id: uuid.UUID
    collab_id: uuid.UUID
    from_profile_id: uuid.UUID
    to_profile_id: uuid.UUID | None
    target: str
    rating: str
    tags: list[str]
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Collaboration list item (GET /collabs)
# ---------------------------------------------------------------------------


class CollabListItem(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    is_read_only: bool
    last_activity_at: datetime
    archived_at: datetime | None
    partner: ParticipantStub
    created_at: datetime

    model_config = {"from_attributes": True}


class CollabListResponse(BaseModel):
    data: list[CollabListItem]
    next_cursor: str | None
    total_count: int


# ---------------------------------------------------------------------------
# Collaboration detail (GET /collabs/{id})
# ---------------------------------------------------------------------------


class CollabDetailOut(BaseModel):
    id: uuid.UUID
    title: str | None
    description: str | None
    status: str
    is_read_only: bool
    last_activity_at: datetime
    nudge_sent_at: datetime | None
    archive_at: datetime | None
    archived_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    participants: list[ParticipantStub]
    status_history: list[StatusEventOut]
    feedback: list[FeedbackOut]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# PATCH /collabs/{id}
# ---------------------------------------------------------------------------


class CollabPatchRequest(BaseModel):
    title: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=2000)


# ---------------------------------------------------------------------------
# POST /collabs/{id}/status
# ---------------------------------------------------------------------------


class StatusTransitionRequest(BaseModel):
    new_status: CollabStatus
    note: str | None = Field(None, max_length=500)


class StatusTransitionResponse(BaseModel):
    id: uuid.UUID
    status: str
    status_event: StatusEventOut


# ---------------------------------------------------------------------------
# POST /collabs/{id}/feedback
# ---------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    target: FeedbackTarget
    rating: FeedbackRating
    tags: list[str] = Field(default_factory=list)
    comment: str | None = Field(None, max_length=500)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        invalid = set(v) - FEEDBACK_TAGS
        if invalid:
            raise ValueError(f"Invalid tags: {invalid}")
        return v


# ---------------------------------------------------------------------------
# POST /collabs/{id}/export
# ---------------------------------------------------------------------------


class ExportRequestResponse(BaseModel):
    export_id: uuid.UUID
    status: str
    requested_at: datetime


class ExportStatusResponse(BaseModel):
    export_id: uuid.UUID
    collab_id: uuid.UUID
    status: str
    pdf_url: str | None = None
    zip_url: str | None = None
    expires_at: datetime | None
    requested_at: datetime
    completed_at: datetime | None


# ---------------------------------------------------------------------------
# History proxy schemas
# ---------------------------------------------------------------------------


class RequestHistoryItem(BaseModel):
    invite_id: uuid.UUID
    counterpart: ParticipantStub
    synopsis: str | None
    status: str
    sent_at: datetime
    responded_at: datetime | None
