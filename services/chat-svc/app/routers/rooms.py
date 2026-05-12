"""
chat-svc REST routers — §10.1 API contracts.

Endpoints:
  GET  /chat/rooms
  GET  /chat/rooms/{room_id}
  GET  /chat/rooms/{room_id}/messages
  POST /chat/rooms/{room_id}/messages
  POST /chat/rooms/{room_id}/messages/{msg_id}/edit
  POST /chat/rooms/{room_id}/read
  GET  /internal/rooms/{room_id}/messages/all   (admin audit)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import ChatMessage, ChatMessageRevision, ChatReadReceipt, ChatRoom
from app.schemas import (
    ChatMessageOut,
    ChatRoomDetail,
    ChatRoomSummary,
    EditMessageBody,
    ProfileStub,
    ReadAckBody,
    ReadReceiptOut,
    SendMessageBody,
    ws_read,
    ws_room_state,
)
from app.uuidv7 import generate_uuidv7

router = APIRouter(prefix="/chat", tags=["chat"])
internal_router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def _require_internal(request: Request) -> None:
    import os
    service = request.headers.get("X-Internal-Service", "")
    if not service and os.environ.get("ENV", "local") not in ("local", "dev"):
        raise HTTPException(status_code=403, detail="Internal endpoint")


def _get_profile_id(request: Request) -> uuid.UUID:
    """Extract profile_id from gateway-injected header or JWT claim."""
    profile_id_str = request.headers.get("X-Profile-Id", "")
    if not profile_id_str:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        return uuid.UUID(profile_id_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid profile ID")


def _msg_to_out(row: Any) -> ChatMessageOut:
    return ChatMessageOut(
        id=row.id,
        room_id=row.room_id,
        sender_profile_id=row.sender_profile_id,
        type=row.type,
        body=row.body,
        media_key=row.media_key,
        mime=row.mime,
        size_bytes=row.size_bytes,
        duration_ms=row.duration_ms,
        reply_to=row.reply_to,
        moderation_status=row.moderation_status,
        edited_at=row.edited_at,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# GET /chat/rooms
# ---------------------------------------------------------------------------


@router.get("/rooms")
async def list_rooms(
    request: Request,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    profile_id = _get_profile_id(request)

    query = text("""
        SELECT id, collaboration_id, participant_ids, state, created_at, archived_at
        FROM chat.chat_room
        WHERE :profile_id = ANY(participant_ids)
          AND (:cursor IS NULL OR id::text > :cursor)
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    result = await db.execute(query, {"profile_id": profile_id, "cursor": cursor, "limit": limit + 1})
    rows = result.fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]

    summaries = []
    for row in rows:
        participants = [ProfileStub(profile_id=pid) for pid in row.participant_ids]

        # Get last message
        msg_result = await db.execute(
            text("""
                SELECT id, room_id, sender_profile_id, type, body, media_key, mime,
                       size_bytes, duration_ms, reply_to, moderation_status, edited_at, created_at
                FROM chat.chat_message
                WHERE room_id = :room_id
                  AND moderation_status IN ('allowed', 'soft_warn')
                  AND deleted_at IS NULL
                ORDER BY id DESC
                LIMIT 1
            """),
            {"room_id": row.id},
        )
        last_msg_row = msg_result.fetchone()
        last_message = _msg_to_out(last_msg_row) if last_msg_row else None

        # Unread count
        receipt_result = await db.execute(
            text("""
                SELECT last_read_msg_id FROM chat.chat_read_receipt
                WHERE room_id = :room_id AND profile_id = :profile_id
            """),
            {"room_id": row.id, "profile_id": profile_id},
        )
        receipt = receipt_result.fetchone()
        since_id = str(receipt.last_read_msg_id) if receipt and receipt.last_read_msg_id else "00000000-0000-0000-0000-000000000000"
        count_result = await db.execute(
            text("""
                SELECT count(*) FROM chat.chat_message
                WHERE room_id = :room_id
                  AND id::text > :since_id
                  AND sender_profile_id <> :profile_id
                  AND deleted_at IS NULL
                  AND moderation_status IN ('allowed', 'soft_warn')
            """),
            {"room_id": row.id, "profile_id": profile_id, "since_id": since_id},
        )
        unread_count = count_result.scalar() or 0

        summaries.append(ChatRoomSummary(
            id=row.id,
            collaboration_id=row.collaboration_id,
            state=row.state,
            participants=participants,
            last_message=last_message,
            unread_count=unread_count,
            created_at=row.created_at,
        ))

    return {
        "rooms": [s.model_dump(mode="json") for s in summaries],
        "next_cursor": str(rows[-1].id) if has_more and rows else None,
    }


# ---------------------------------------------------------------------------
# GET /chat/rooms/{room_id}
# ---------------------------------------------------------------------------


@router.get("/rooms/{room_id}")
async def get_room(
    room_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    profile_id = _get_profile_id(request)

    result = await db.execute(select(ChatRoom).where(ChatRoom.id == room_id))
    room = result.scalar_one_or_none()
    if not room or profile_id not in room.participant_ids:
        raise HTTPException(status_code=404, detail="Room not found")

    # Read receipts
    rr_result = await db.execute(
        select(ChatReadReceipt).where(ChatReadReceipt.room_id == room_id)
    )
    receipts = rr_result.scalars().all()

    participants = [ProfileStub(profile_id=pid) for pid in room.participant_ids]
    read_receipts = [
        ReadReceiptOut(
            profile_id=r.profile_id,
            last_read_msg_id=r.last_read_msg_id,
            last_read_at=r.last_read_at,
        )
        for r in receipts
    ]

    return ChatRoomDetail(
        id=room.id,
        collaboration_id=room.collaboration_id,
        state=room.state,
        participants=participants,
        read_receipts=read_receipts,
        created_at=room.created_at,
        archived_at=room.archived_at,
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# GET /chat/rooms/{room_id}/messages
# ---------------------------------------------------------------------------


@router.get("/rooms/{room_id}/messages")
async def get_messages(
    room_id: uuid.UUID,
    request: Request,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    direction: str = Query(default="before"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    profile_id = _get_profile_id(request)

    result = await db.execute(select(ChatRoom).where(ChatRoom.id == room_id))
    room = result.scalar_one_or_none()
    if not room or profile_id not in room.participant_ids:
        raise HTTPException(status_code=404, detail="Room not found")

    if direction == "after":
        query = text("""
            SELECT id, room_id, sender_profile_id, type, body, media_key, mime,
                   size_bytes, duration_ms, reply_to, moderation_status, edited_at, created_at
            FROM chat.chat_message
            WHERE room_id = :room_id
              AND (:cursor IS NULL OR id::text > :cursor)
              AND moderation_status IN ('allowed', 'soft_warn')
              AND deleted_at IS NULL
            ORDER BY id ASC
            LIMIT :limit
        """)
    else:
        query = text("""
            SELECT id, room_id, sender_profile_id, type, body, media_key, mime,
                   size_bytes, duration_ms, reply_to, moderation_status, edited_at, created_at
            FROM chat.chat_message
            WHERE room_id = :room_id
              AND (:cursor IS NULL OR id::text < :cursor)
              AND moderation_status IN ('allowed', 'soft_warn')
              AND deleted_at IS NULL
            ORDER BY id DESC
            LIMIT :limit
        """)

    msg_result = await db.execute(query, {"room_id": room_id, "cursor": cursor, "limit": limit + 1})
    rows = msg_result.fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]

    messages = [_msg_to_out(r) for r in rows]
    next_cursor = str(rows[-1].id) if has_more and rows else None

    return {
        "messages": [m.model_dump(mode="json") for m in messages],
        "next_cursor": next_cursor,
    }


# ---------------------------------------------------------------------------
# POST /chat/rooms/{room_id}/messages
# ---------------------------------------------------------------------------


@router.post("/rooms/{room_id}/messages", status_code=201)
async def send_message(
    room_id: uuid.UUID,
    body: SendMessageBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """REST equivalent of WS `send` — same moderation logic applied."""
    profile_id = _get_profile_id(request)

    result = await db.execute(select(ChatRoom).where(ChatRoom.id == room_id))
    room = result.scalar_one_or_none()
    if not room or profile_id not in room.participant_ids:
        raise HTTPException(status_code=404, detail="Room not found")

    if room.state != "open":
        raise HTTPException(status_code=403, detail="Room is read-only")

    # Import and reuse WS handler moderation logic
    from app.ws.handler import _call_moderation
    import httpx

    scan = await _call_moderation(body.body)
    score = scan.get("score", 0.0)

    if score >= 0.9:
        mod_status = "auto_hidden"
    elif 0.7 <= score < 0.9:
        mod_status = "hidden"
    elif 0.4 <= score < 0.7:
        mod_status = "soft_warn"
    else:
        mod_status = "allowed"

    msg = ChatMessage(
        id=generate_uuidv7(),
        room_id=room_id,
        sender_profile_id=profile_id,
        type="text",
        body=body.body,
        client_nonce=body.client_nonce,
        reply_to=body.reply_to,
        moderation_score=score,
        moderation_status=mod_status,
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    return ChatMessageOut(
        id=msg.id,
        room_id=msg.room_id,
        sender_profile_id=msg.sender_profile_id,
        type=msg.type,
        body=msg.body,
        moderation_status=msg.moderation_status,
        created_at=msg.created_at,
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# POST /chat/rooms/{room_id}/messages/{msg_id}/edit
# ---------------------------------------------------------------------------


@router.post("/rooms/{room_id}/messages/{msg_id}/edit")
async def edit_message(
    room_id: uuid.UUID,
    msg_id: uuid.UUID,
    body: EditMessageBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    profile_id = _get_profile_id(request)

    result = await db.execute(
        text("""
            SELECT id, room_id, sender_profile_id, type, body, media_key, mime,
                   size_bytes, duration_ms, reply_to, moderation_status, edited_at, created_at,
                   deleted_at
            FROM chat.chat_message
            WHERE id = :msg_id AND room_id = :room_id
        """),
        {"msg_id": msg_id, "room_id": room_id},
    )
    msg_row = result.fetchone()
    if not msg_row:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg_row.sender_profile_id != profile_id:
        raise HTTPException(status_code=403, detail="Cannot edit another user's message")
    if msg_row.type != "text":
        raise HTTPException(status_code=400, detail="Only text messages can be edited")
    if msg_row.deleted_at:
        raise HTTPException(status_code=410, detail="Message deleted")

    # Determine current version
    ver_result = await db.execute(
        text("""
            SELECT COALESCE(MAX(version), 0) as max_ver
            FROM chat.chat_message_revision
            WHERE msg_id = :msg_id
        """),
        {"msg_id": msg_id},
    )
    max_ver = ver_result.scalar() or 0

    # If first edit, save original body as version 1
    if max_ver == 0:
        db.add(ChatMessageRevision(
            msg_id=msg_id,
            version=1,
            body=msg_row.body or "",
            edited_at=msg_row.created_at,
        ))

    new_version = max(max_ver, 1) + 1
    now = datetime.now(tz=timezone.utc)
    db.add(ChatMessageRevision(msg_id=msg_id, version=new_version, body=body.body, edited_at=now))

    await db.execute(
        text("""
            UPDATE chat.chat_message
            SET body = :body, edited_at = :now
            WHERE id = :msg_id
        """),
        {"body": body.body, "now": now, "msg_id": msg_id},
    )
    await db.commit()

    return ChatMessageOut(
        id=msg_row.id,
        room_id=msg_row.room_id,
        sender_profile_id=msg_row.sender_profile_id,
        type=msg_row.type,
        body=body.body,
        moderation_status=msg_row.moderation_status,
        edited_at=now,
        created_at=msg_row.created_at,
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# POST /chat/rooms/{room_id}/read
# ---------------------------------------------------------------------------


@router.post("/rooms/{room_id}/read", status_code=204)
async def mark_read(
    room_id: uuid.UUID,
    body: ReadAckBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    profile_id = _get_profile_id(request)

    result = await db.execute(select(ChatRoom).where(ChatRoom.id == room_id))
    room = result.scalar_one_or_none()
    if not room or profile_id not in room.participant_ids:
        raise HTTPException(status_code=404, detail="Room not found")

    now = datetime.now(tz=timezone.utc)
    await db.execute(
        text("""
            INSERT INTO chat.chat_read_receipt (room_id, profile_id, last_read_msg_id, last_read_at)
            VALUES (:room_id, :profile_id, :msg_id, :now)
            ON CONFLICT (room_id, profile_id)
            DO UPDATE SET
                last_read_msg_id = EXCLUDED.last_read_msg_id,
                last_read_at     = EXCLUDED.last_read_at
            WHERE EXCLUDED.last_read_msg_id::text > chat_read_receipt.last_read_msg_id::text
               OR chat_read_receipt.last_read_msg_id IS NULL
        """),
        {"room_id": room_id, "profile_id": profile_id, "msg_id": body.up_to_msg_id, "now": now},
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Internal audit endpoint
# ---------------------------------------------------------------------------


@internal_router.get("/rooms/{room_id}/messages/all")
async def audit_messages(
    room_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """All messages + revisions in chronological order. Admin-only."""
    _require_internal(request)

    msg_result = await db.execute(
        text("""
            SELECT id, room_id, sender_profile_id, type, body, media_key, mime,
                   size_bytes, duration_ms, reply_to, moderation_status, edited_at,
                   deleted_at, moderation_score, created_at
            FROM chat.chat_message
            WHERE room_id = :room_id
            ORDER BY id ASC
        """),
        {"room_id": room_id},
    )
    msgs = msg_result.fetchall()

    rev_result = await db.execute(
        text("""
            SELECT msg_id, version, body, edited_at
            FROM chat.chat_message_revision
            WHERE msg_id IN (
                SELECT id FROM chat.chat_message WHERE room_id = :room_id
            )
            ORDER BY msg_id, version ASC
        """),
        {"room_id": room_id},
    )
    revisions = rev_result.fetchall()
    rev_map: dict[str, list] = {}
    for r in revisions:
        key = str(r.msg_id)
        rev_map.setdefault(key, []).append(
            {"version": r.version, "body": r.body, "edited_at": r.edited_at.isoformat() if r.edited_at else None}
        )

    result_msgs = []
    for m in msgs:
        result_msgs.append({
            "id": str(m.id),
            "room_id": str(m.room_id),
            "sender_profile_id": str(m.sender_profile_id),
            "type": m.type,
            "body": m.body,
            "media_key": m.media_key,
            "moderation_status": m.moderation_status,
            "moderation_score": m.moderation_score,
            "created_at": m.created_at.isoformat(),
            "edited_at": m.edited_at.isoformat() if m.edited_at else None,
            "deleted_at": m.deleted_at.isoformat() if m.deleted_at else None,
            "revisions": rev_map.get(str(m.id), []),
        })

    return {"room_id": str(room_id), "messages": result_msgs}
