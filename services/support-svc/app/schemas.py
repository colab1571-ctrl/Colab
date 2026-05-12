"""
support-svc Pydantic schemas (request/response models).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# FAQ / KbArticle
# ---------------------------------------------------------------------------


class KbArticleOut(BaseModel):
    slug: str
    title: str
    body_md: str
    tags: list[str]
    updated_at: datetime

    model_config = {"from_attributes": True}


class KbArticleListOut(BaseModel):
    articles: list[KbArticleOut]


# ---------------------------------------------------------------------------
# Chatbot
# ---------------------------------------------------------------------------


class ChatbotRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: uuid.UUID | None = None
    ticket_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

VALID_CATEGORIES = {
    "harassment_threats",
    "ip_dmca",
    "payment",
    "technical",
    "other",
}

VALID_STATUSES = {"open", "in_progress", "pending_user", "resolved", "closed"}


class TicketCreate(BaseModel):
    category: str
    subject: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1, max_length=8000)
    attachments: list[str] = Field(default_factory=list)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(f"category must be one of {VALID_CATEGORIES}")
        return v


class TicketOut(BaseModel):
    id: uuid.UUID
    category: str
    subject: str
    body: str
    status: str
    priority: str
    tier_at_creation: str
    sla_ack_due: datetime
    sla_resolve_due: datetime
    sla_paused_seconds: int
    sla_ack_breached_at: datetime | None
    sla_resolve_breached_at: datetime | None
    first_response_at: datetime | None
    resolved_at: datetime | None
    assigned_to: uuid.UUID | None
    moderation_case_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TicketEventOut(BaseModel):
    id: uuid.UUID
    kind: str
    actor: str
    actor_id: uuid.UUID | None
    body: str | None
    metadata: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketDetailOut(BaseModel):
    ticket: TicketOut
    events: list[TicketEventOut]


class TicketListOut(BaseModel):
    tickets: list[TicketOut]
    total: int
    page: int
    per_page: int


class ReplyCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=8000)
    attachments: list[str] = Field(default_factory=list)


class ReplyOut(BaseModel):
    event_id: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# CSAT
# ---------------------------------------------------------------------------


class CSATCreate(BaseModel):
    score: int = Field(..., ge=1, le=5)
    comment: str | None = Field(None, max_length=1000)


class CSATOut(BaseModel):
    csat_id: uuid.UUID


# ---------------------------------------------------------------------------
# Status page
# ---------------------------------------------------------------------------


class StatusComponentOut(BaseModel):
    name: str
    status: str


class StatusOut(BaseModel):
    status: str
    description: str
    incidents: list[dict[str, Any]]
    components: list[StatusComponentOut]
    fetched_at: datetime
