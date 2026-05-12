"""Pydantic schemas for MockupConsent API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConsentRequest(BaseModel):
    lifespan_days: Literal[1, 14] = 1
    brief: str = Field(default="", max_length=500)
    kind: Literal["image", "audio", "both"] = "image"


class ConsentCreatedResponse(BaseModel):
    consent_id: uuid.UUID
    status: str
    message: str


class ConsentApprovedResponse(BaseModel):
    consent_id: uuid.UUID
    status: str
    ai_interaction_id: uuid.UUID
    estimated_seconds: int


class MockupAssetOut(BaseModel):
    id: uuid.UUID
    consent_id: uuid.UUID | None
    kind: str
    active: bool
    generated_at: datetime | None
    expires_at: datetime | None
    signed_url: str
    signed_url_expires_at: datetime
    watermark_present: bool = True


class MockupListResponse(BaseModel):
    mockups: list[MockupAssetOut]


class ScreenshotEventRequest(BaseModel):
    platform: Literal["ios", "android"]
    detected_at: datetime
