"""Pydantic schemas for AI command API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Command request
# ---------------------------------------------------------------------------

class CommandArgs(BaseModel):
    prompt: str | None = None
    n: int = Field(default=50, ge=5, le=200)


class CommandRequest(BaseModel):
    command: Literal[
        "summarize-chat", "brainstorm", "palette", "mockup-image", "mockup-audio"
    ]
    args: CommandArgs = Field(default_factory=CommandArgs)


# ---------------------------------------------------------------------------
# Synchronous result (text commands)
# ---------------------------------------------------------------------------

class AITextResult(BaseModel):
    type: Literal["ai_text"] = "ai_text"
    command: str
    body: str
    ai_interaction_id: uuid.UUID
    input_tokens: int | None = None
    output_tokens: int | None = None


class AIPaletteColor(BaseModel):
    name: str
    hex: str
    usage_note: str


class AIPaletteResult(BaseModel):
    type: Literal["ai_palette"] = "ai_palette"
    command: str = "palette"
    colors: list[AIPaletteColor]
    ai_interaction_id: uuid.UUID


class CommandSyncResponse(BaseModel):
    ai_interaction_id: uuid.UUID
    command: str
    result: AITextResult | AIPaletteResult
    credits_charged: int
    credits_remaining: int | None = None


# ---------------------------------------------------------------------------
# Async result (image/audio commands)
# ---------------------------------------------------------------------------

class CommandAsyncResponse(BaseModel):
    ai_interaction_id: uuid.UUID
    mockup_asset_id: uuid.UUID
    status: Literal["queued"] = "queued"
    estimated_seconds: int


# ---------------------------------------------------------------------------
# Upsell / error
# ---------------------------------------------------------------------------

class UpsellPayload(BaseModel):
    tier: str = "premium"
    cta_url: str = "https://app.colab.app/upgrade"


class InsufficientCreditsError(BaseModel):
    error: Literal["insufficient_credits"] = "insufficient_credits"
    upsell: UpsellPayload = Field(default_factory=UpsellPayload)
