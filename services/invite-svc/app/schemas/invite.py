"""
invite-svc — Pydantic request/response schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Shared enums (string literals for Pydantic v2)
# ---------------------------------------------------------------------------

InviteStatus = Literal["pending", "accepted", "rejected", "expired", "cancelled"]
BlockReason = Literal["harassment", "spam", "inappropriate_content", "other"]


# ---------------------------------------------------------------------------
# Invite schemas
# ---------------------------------------------------------------------------


class SendInviteRequest(BaseModel):
    to_profile_id: uuid.UUID
    synopsis: str = Field(..., min_length=1, max_length=250)

    @field_validator("synopsis")
    @classmethod
    def strip_synopsis(cls, v: str) -> str:
        return v.strip()


class SendInviteResponse(BaseModel):
    invite_id: uuid.UUID
    status: InviteStatus
    quota_remaining: int
    archive_at: datetime


class QuotaExceededResponse(BaseModel):
    error: Literal["quota_exceeded"] = "quota_exceeded"
    quota_remaining: int = 0
    upsell: bool = True


class BlockedResponse(BaseModel):
    error: Literal["blocked"] = "blocked"


class SynopsisFlaggedResponse(BaseModel):
    error: Literal["synopsis_flagged"] = "synopsis_flagged"
    reason: str | None = None


class AcceptInviteResponse(BaseModel):
    invite_id: uuid.UUID
    status: Literal["accepted"]
    matched: bool


class RejectInviteResponse(BaseModel):
    invite_id: uuid.UUID
    status: Literal["rejected"]


class CancelInviteResponse(BaseModel):
    invite_id: uuid.UUID
    status: Literal["cancelled"]


# ---------------------------------------------------------------------------
# Profile card embedded in invite list responses
# ---------------------------------------------------------------------------


class ProfileCard(BaseModel):
    profile_id: uuid.UUID
    display_name: str | None
    avatar_url: str | None
    city: str | None
    top_vocation: str | None


class InviteCard(BaseModel):
    invite_id: uuid.UUID
    from_profile: ProfileCard | None
    to_profile: ProfileCard | None
    synopsis: str
    status: InviteStatus
    created_at: datetime
    archive_at: datetime
    ai_match_score: float | None
    responded_at: datetime | None


class InviteListResponse(BaseModel):
    items: list[InviteCard]
    next_cursor: str | None
    total_pending: int


# ---------------------------------------------------------------------------
# Block schemas
# ---------------------------------------------------------------------------


class CreateBlockRequest(BaseModel):
    reason: BlockReason | None = None


class BlockResponse(BaseModel):
    blocker_id: uuid.UUID
    blocked_id: uuid.UUID
    created_at: datetime


class UnblockResponse(BaseModel):
    unblocked: bool = True


class BlockCard(BaseModel):
    profile_id: uuid.UUID
    display_name: str | None
    avatar_url: str | None
    blocked_at: datetime


class BlockListResponse(BaseModel):
    items: list[BlockCard]
    next_cursor: str | None
