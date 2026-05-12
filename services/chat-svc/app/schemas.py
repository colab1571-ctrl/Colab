"""
chat-svc Pydantic schemas — wire format for REST and WebSocket frames.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared stubs
# ---------------------------------------------------------------------------


class ProfileStub(BaseModel):
    profile_id: uuid.UUID
    display_name: str | None = None
    avatar_url: str | None = None


class ReplyPreview(BaseModel):
    id: uuid.UUID
    sender_profile_id: uuid.UUID
    type: str
    body: str | None = None
    media_url: str | None = None


# ---------------------------------------------------------------------------
# ChatMessageOut — primary envelope sent over WS and REST
# ---------------------------------------------------------------------------


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    sender_profile_id: uuid.UUID
    sender: ProfileStub | None = None
    type: str
    body: str | None = None
    media_key: str | None = None
    media_url: str | None = None  # CloudFront signed URL
    mime: str | None = None
    size_bytes: int | None = None
    duration_ms: int | None = None
    reply_to: uuid.UUID | None = None
    reply_preview: ReplyPreview | None = None
    moderation_status: str = "allowed"
    edited_at: datetime | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# ChatRoomSummary + Detail
# ---------------------------------------------------------------------------


class ChatRoomSummary(BaseModel):
    id: uuid.UUID
    collaboration_id: uuid.UUID
    state: str
    participants: list[ProfileStub]
    last_message: ChatMessageOut | None = None
    unread_count: int = 0
    created_at: datetime


class ReadReceiptOut(BaseModel):
    profile_id: uuid.UUID
    last_read_msg_id: uuid.UUID | None
    last_read_at: datetime | None


class ChatRoomDetail(BaseModel):
    id: uuid.UUID
    collaboration_id: uuid.UUID
    state: str
    participants: list[ProfileStub]
    read_receipts: list[ReadReceiptOut]
    created_at: datetime
    archived_at: datetime | None = None


# ---------------------------------------------------------------------------
# REST request bodies
# ---------------------------------------------------------------------------


class SendMessageBody(BaseModel):
    body: str = Field(..., max_length=4000)
    reply_to: uuid.UUID | None = None
    client_nonce: uuid.UUID


class EditMessageBody(BaseModel):
    body: str = Field(..., max_length=4000)


class ReadAckBody(BaseModel):
    up_to_msg_id: uuid.UUID


# ---------------------------------------------------------------------------
# WebSocket frame types (client → server)
# ---------------------------------------------------------------------------


class WSSendPayload(BaseModel):
    body: str = Field(..., max_length=4000)
    reply_to: uuid.UUID | None = None
    client_nonce: uuid.UUID


class WSTypingPayload(BaseModel):
    state: Literal["start", "stop"]


class WSReadAckPayload(BaseModel):
    up_to_msg_id: uuid.UUID


class WSReconnectPayload(BaseModel):
    since_msg_id: uuid.UUID


class WSFrame(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    request_id: uuid.UUID | None = None
    ts: str | None = None


# ---------------------------------------------------------------------------
# WebSocket frame builders (server → client)
# ---------------------------------------------------------------------------


def ws_message(msg: ChatMessageOut) -> dict:
    return {"type": "message", "payload": msg.model_dump(mode="json")}


def ws_message_ack(client_nonce: uuid.UUID, msg_id: uuid.UUID, created_at: datetime) -> dict:
    return {
        "type": "message_ack",
        "payload": {
            "client_nonce": str(client_nonce),
            "msg_id": str(msg_id),
            "created_at": created_at.isoformat(),
        },
    }


def ws_typing(profile_id: uuid.UUID, state: str) -> dict:
    return {
        "type": "typing",
        "payload": {"profile_id": str(profile_id), "state": state},
    }


def ws_presence(profile_id: uuid.UUID, online: bool, last_seen_at: str) -> dict:
    return {
        "type": "presence",
        "payload": {
            "profile_id": str(profile_id),
            "online": online,
            "last_seen_at": last_seen_at,
        },
    }


def ws_read(profile_id: uuid.UUID, up_to_msg_id: uuid.UUID, read_at: datetime) -> dict:
    return {
        "type": "read",
        "payload": {
            "profile_id": str(profile_id),
            "up_to_msg_id": str(up_to_msg_id),
            "read_at": read_at.isoformat(),
        },
    }


def ws_replay(messages: list[ChatMessageOut], has_more: bool) -> dict:
    return {
        "type": "replay",
        "payload": {
            "messages": [m.model_dump(mode="json") for m in messages],
            "has_more": has_more,
        },
    }


def ws_room_state(state: str) -> dict:
    return {"type": "room_state", "payload": {"state": state}}


def ws_error(code: str, message: str, request_id: str | None = None) -> dict:
    payload: dict = {"code": code, "message": message}
    if request_id:
        payload["request_id"] = request_id
    return {"type": "error", "payload": payload}


def ws_pong() -> dict:
    return {"type": "pong", "payload": {}}


def ws_connection_expiry_warning(expires_in_seconds: int) -> dict:
    return {
        "type": "connection_expiry_warning",
        "payload": {"expires_in_seconds": expires_in_seconds},
    }


def ws_soft_warn_ack(msg: ChatMessageOut) -> dict:
    return {
        "type": "message_ack",
        "payload": {
            **msg.model_dump(mode="json"),
            "warning": "This message may have violated community guidelines.",
        },
    }
