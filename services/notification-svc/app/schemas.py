"""
notification-svc Pydantic schemas — request/response + event payloads.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Notification API schemas
# ---------------------------------------------------------------------------


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    payload: dict[str, Any]
    in_app_seen_at: datetime | None
    delivered_push_at: datetime | None
    delivered_email_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    items: list[NotificationOut]
    next_cursor: str | None
    has_more: bool


class NotificationReadResponse(BaseModel):
    id: uuid.UUID
    in_app_seen_at: datetime


class ReadAllResponse(BaseModel):
    updated_count: int


# ---------------------------------------------------------------------------
# Preference schemas
# ---------------------------------------------------------------------------


class PreferenceOut(BaseModel):
    type: str
    channel: str
    enabled: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class PreferencesResponse(BaseModel):
    preferences: list[PreferenceOut]


class PreferenceUpdate(BaseModel):
    type: str
    channel: str
    enabled: bool


class PatchPreferencesRequest(BaseModel):
    updates: list[PreferenceUpdate] = Field(..., max_length=33)


class PatchPreferencesResponse(BaseModel):
    updated: list[PreferenceOut]


# ---------------------------------------------------------------------------
# Device schemas
# ---------------------------------------------------------------------------


class RegisterDeviceRequest(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=255)
    platform: str = Field(..., pattern="^(ios|android)$")
    expo_push_token: str | None = None
    device_token: str | None = None
    app_version: str | None = None
    os_version: str | None = None


class RegisterDeviceResponse(BaseModel):
    device_id: str
    registered: bool
    should_prompt_push: bool
    queued_count: int


# ---------------------------------------------------------------------------
# Event payload schemas (validated by consumers)
# ---------------------------------------------------------------------------


class MatchCreatedEvent(BaseModel):
    match_id: uuid.UUID
    user_id_a: uuid.UUID
    user_id_b: uuid.UUID
    collab_id: uuid.UUID
    user_a_display_name: str
    user_b_display_name: str
    user_a_avatar_url: str | None = None
    user_b_avatar_url: str | None = None


class InviteSentEvent(BaseModel):
    invite_id: uuid.UUID
    sender_user_id: uuid.UUID
    recipient_user_id: uuid.UUID
    sender_display_name: str
    sender_avatar_url: str | None = None
    synopsis: str = Field(..., max_length=250)


class InviteAcceptedEvent(BaseModel):
    invite_id: uuid.UUID
    sender_user_id: uuid.UUID  # original sender gets notified
    acceptor_user_id: uuid.UUID
    acceptor_display_name: str
    acceptor_avatar_url: str | None = None
    collab_id: uuid.UUID


class ChatMessageSentEvent(BaseModel):
    collab_id: uuid.UUID
    message_id: uuid.UUID
    sender_user_id: uuid.UUID
    recipient_user_id: uuid.UUID
    sender_display_name: str
    message_preview: str = Field(..., max_length=100)
    message_type: str = Field(default="text", pattern="^(text|voice|file|link)$")


class ChatFileSentEvent(BaseModel):
    collab_id: uuid.UUID
    message_id: uuid.UUID
    sender_user_id: uuid.UUID
    recipient_user_id: uuid.UUID
    sender_display_name: str
    file_name: str
    file_type: str = Field(..., pattern="^(image|audio|video|document)$")
    file_size_bytes: int


class AIMockupGeneratedEvent(BaseModel):
    collab_id: uuid.UUID
    mockup_id: uuid.UUID
    user_id_a: uuid.UUID
    user_id_b: uuid.UUID
    mockup_type: str = Field(..., pattern="^(image|audio)$")
    preview_url: str | None = None
    consent_set_id: uuid.UUID
    expires_at: datetime


class CollabNudgeDueEvent(BaseModel):
    collab_id: uuid.UUID
    user_id_a: uuid.UUID
    user_id_b: uuid.UUID
    user_a_display_name: str
    user_b_display_name: str
    inactive_days: int
    auto_archive_at: datetime
    nudge_cycle_date: str  # YYYY-MM-DD for idempotency


class CollabStatusUpdatedEvent(BaseModel):
    collab_id: uuid.UUID
    changed_by_user_id: uuid.UUID
    other_user_id: uuid.UUID
    other_user_display_name: str
    new_status: str = Field(..., pattern="^(in_progress|completed|didnt_work_out)$")


class SupportTicketRepliedEvent(BaseModel):
    ticket_id: uuid.UUID
    user_id: uuid.UUID
    ticket_subject: str
    reply_preview: str = Field(..., max_length=150)
    replied_by: str = Field(..., pattern="^(agent|ai)$")


class MarketingBroadcastEvent(BaseModel):
    campaign_id: uuid.UUID
    title: str
    body: str
    action_url: str | None = None
    segment: str = Field(..., pattern="^(all|premium|free)$")


class UserCreatedEvent(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
