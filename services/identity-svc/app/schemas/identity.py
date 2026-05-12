"""identity-svc — Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class InquiryStartResponse(BaseModel):
    """Response from POST /identity/inquiry/start."""

    persona_inquiry_id: str
    persona_session_token: str


class IdentityVerificationOut(BaseModel):
    """GET /identity/verification — current state for the calling user."""

    user_id: uuid.UUID
    persona_inquiry_id: str | None
    status: str
    face_age_signal: str | None
    decision_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PersonaWebhookPayload(BaseModel):
    """
    Minimal envelope for Persona webhook.
    We keep the raw body for HMAC verification; this schema
    covers the fields we actually consume.
    """

    model_config = {"extra": "allow"}
