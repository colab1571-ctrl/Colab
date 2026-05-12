"""
chat-svc — WebSocket frame handler.

Entry point: handle_room_ws(ws, room_id, profile_id, app_state)

Implements §3 (wire protocol), §4 (reconnect+resume), §6 (block-aware),
§7 (read receipts), §9 (moderation integration).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import httpx
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_chat_settings
from app.models import (
    ChatMessage,
    ChatMessageRevision,
    ChatReadReceipt,
    ChatRoom,
)
from app.schemas import (
    ChatMessageOut,
    WSSendPayload,
    WSTypingPayload,
    WSReadAckPayload,
    WSReconnectPayload,
    ws_error,
    ws_message,
    ws_message_ack,
    ws_pong,
    ws_presence,
    ws_read,
    ws_replay,
    ws_room_state,
    ws_soft_warn_ack,
    ws_typing,
    ws_connection_expiry_warning,
)
from app.ws.connection_manager import AsyncConnectionManager
from app.ws.presence import AsyncPresenceManager
from app.uuidv7 import generate_uuidv7

logger = logging.getLogger(__name__)

_settings = get_chat_settings()

# Per-connection rate-limit counters (in-process, reset each minute)
_rate_counters: dict[int, dict] = defaultdict(
    lambda: {"sends": 0, "read_acks": 0, "reconnects": 0, "typing_last": 0.0, "minute": 0}
)


def _rate_check_send(ws_id: int) -> bool:
    c = _rate_counters[ws_id]
    now_min = int(time.time() // 60)
    if c["minute"] != now_min:
        c["sends"] = 0
        c["read_acks"] = 0
        c["minute"] = now_min
    if c["sends"] >= _settings.send_rate_per_minute:
        return False
    c["sends"] += 1
    return True


def _rate_check_typing(ws_id: int) -> bool:
    c = _rate_counters[ws_id]
    now = time.monotonic()
    if now - c["typing_last"] < _settings.typing_rate_seconds:
        return False
    c["typing_last"] = now
    return True


def _rate_check_read_ack(ws_id: int) -> bool:
    c = _rate_counters[ws_id]
    now_min = int(time.time() // 60)
    if c["minute"] != now_min:
        c["sends"] = 0
        c["read_acks"] = 0
        c["minute"] = now_min
    if c["read_acks"] >= _settings.read_ack_rate_per_minute:
        return False
    c["read_acks"] += 1
    return True


def _rate_check_reconnect(ws_id: int) -> bool:
    c = _rate_counters[ws_id]
    if c["reconnects"] >= _settings.max_reconnect_frames:
        return False
    c["reconnects"] += 1
    return True


async def _call_moderation(body: str) -> dict:
    """
    Call moderation-svc /internal/scan/text.
    Returns {"score": float, "decision": str, "categories": list}.
    On timeout (>250ms) → allow through with status 'pending' (circuit-break).
    """
    timeout = _settings.moderation_scan_timeout_ms / 1000
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{_settings.moderation_svc_url}/internal/scan/text",
                json={"text": body, "ctx": {"context": "chat_message"}},
                headers={"X-Internal-Service": "chat-svc"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("Moderation scan failed/timeout: %s — allowing through", exc)
        return {"score": 0.0, "decision": "allow", "categories": []}


async def _build_message_out(
    msg: ChatMessage, db: AsyncSession
) -> ChatMessageOut:
    """Build ChatMessageOut from ORM row, including reply_preview if needed."""
    reply_preview = None
    if msg.reply_to:
        result = await db.execute(
            select(ChatMessage).where(ChatMessage.id == msg.reply_to)
        )
        parent = result.scalar_one_or_none()
        if parent:
            from app.schemas import ReplyPreview
            reply_preview = ReplyPreview(
                id=parent.id,
                sender_profile_id=parent.sender_profile_id,
                type=parent.type,
                body=parent.body,
            )

    return ChatMessageOut(
        id=msg.id,
        room_id=msg.room_id,
        sender_profile_id=msg.sender_profile_id,
        type=msg.type,
        body=msg.body,
        media_key=msg.media_key,
        mime=msg.mime,
        size_bytes=msg.size_bytes,
        duration_ms=msg.duration_ms,
        reply_to=msg.reply_to,
        reply_preview=reply_preview,
        moderation_status=msg.moderation_status,
        edited_at=msg.edited_at,
        created_at=msg.created_at,
    )


async def _handle_send(
    ws: WebSocket,
    ws_id: int,
    payload: dict,
    room: ChatRoom,
    profile_id: uuid.UUID,
    db: AsyncSession,
    presence: AsyncPresenceManager,
    conn_mgr: AsyncConnectionManager,
    request_id: str | None,
) -> None:
    """Handle `send` frame — moderation → persist → broadcast."""
    if not _rate_check_send(ws_id):
        await conn_mgr.send_to(ws, ws_error("RATE_LIMITED", "Too many messages", request_id))
        return

    try:
        send_payload = WSSendPayload(**payload)
    except Exception:
        await conn_mgr.send_to(ws, ws_error("INTERNAL_ERROR", "Invalid payload", request_id))
        return

    if room.state != "open":
        await conn_mgr.send_to(ws, ws_error("ROOM_READ_ONLY", "Room is read-only", request_id))
        return

    if len(send_payload.body) > _settings.max_body_length:
        await conn_mgr.send_to(
            ws, ws_error("MESSAGE_TOO_LONG", "Body exceeds 4000 characters", request_id)
        )
        return

    # Dedup check
    if send_payload.client_nonce:
        existing = await db.execute(
            select(ChatMessage).where(
                ChatMessage.client_nonce == send_payload.client_nonce
            )
        )
        if existing.scalar_one_or_none():
            # Already persisted — just send ack
            msg_row = existing.scalar_one_or_none()
            if msg_row:
                msg_out = await _build_message_out(msg_row, db)
                await conn_mgr.send_to(
                    ws,
                    ws_message_ack(send_payload.client_nonce, msg_row.id, msg_row.created_at),
                )
            return

    # Moderation scan
    scan = await _call_moderation(send_payload.body)
    score = scan.get("score", 0.0)
    categories = scan.get("categories", [])
    has_escalate_categories = any(
        c in categories for c in ("harassment_threat", "dmca")
    )

    if score >= 0.9 or has_escalate_categories:
        msg = ChatMessage(
            id=generate_uuidv7(),
            room_id=room.id,
            sender_profile_id=profile_id,
            type="text",
            body=send_payload.body,
            client_nonce=send_payload.client_nonce,
            reply_to=send_payload.reply_to,
            moderation_score=score,
            moderation_status="auto_hidden",
            created_at=datetime.now(tz=timezone.utc),
        )
        db.add(msg)
        await db.commit()
        # Publish moderation event (fire-and-forget)
        asyncio.ensure_future(
            _publish_moderation_event(room.id, msg.id, profile_id, score, "auto_hide_temp_mute")
        )
        await conn_mgr.send_to(
            ws,
            ws_error("MODERATION_REJECTED", "Message not delivered: community guidelines", request_id),
        )
        return

    if 0.7 <= score < 0.9:
        msg = ChatMessage(
            id=generate_uuidv7(),
            room_id=room.id,
            sender_profile_id=profile_id,
            type="text",
            body=send_payload.body,
            client_nonce=send_payload.client_nonce,
            reply_to=send_payload.reply_to,
            moderation_score=score,
            moderation_status="hidden",
            created_at=datetime.now(tz=timezone.utc),
        )
        db.add(msg)
        await db.commit()
        asyncio.ensure_future(
            _publish_moderation_event(room.id, msg.id, profile_id, score, "hold_for_review")
        )
        await conn_mgr.send_to(
            ws, ws_error("MODERATION_HOLD", "Message held for review", request_id)
        )
        return

    if 0.4 <= score < 0.7:
        mod_status = "soft_warn"
    else:
        mod_status = "allowed"

    msg = ChatMessage(
        id=generate_uuidv7(),
        room_id=room.id,
        sender_profile_id=profile_id,
        type="text",
        body=send_payload.body,
        client_nonce=send_payload.client_nonce,
        reply_to=send_payload.reply_to,
        moderation_score=score,
        moderation_status=mod_status,
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    msg_out = await _build_message_out(msg, db)

    # Publish to Redis (cross-pod fanout)
    await presence.publish(room.id, ws_message(msg_out))

    # Ack to sender
    if mod_status == "soft_warn":
        await conn_mgr.send_to(ws, ws_soft_warn_ack(msg_out))
    else:
        await conn_mgr.send_to(
            ws, ws_message_ack(send_payload.client_nonce, msg.id, msg.created_at)
        )

    # Publish chat.message.sent event
    asyncio.ensure_future(_publish_chat_event(room.id, msg_out))


async def _publish_moderation_event(
    room_id: uuid.UUID, msg_id: uuid.UUID, profile_id: uuid.UUID, score: float, action: str
) -> None:
    """Publish moderation event to RabbitMQ (best-effort)."""
    import os
    try:
        import aio_pika
        conn = await aio_pika.connect_robust(
            os.environ.get("RABBITMQ_URL", "amqp://colab:colab@localhost:5672/")
        )
        async with conn:
            channel = await conn.channel()
            exchange = await channel.declare_exchange("moderation", aio_pika.ExchangeType.TOPIC)
            await exchange.publish(
                aio_pika.Message(
                    body=json.dumps({
                        "event": "moderation.action_taken",
                        "room_id": str(room_id),
                        "msg_id": str(msg_id),
                        "profile_id": str(profile_id),
                        "score": score,
                        "action": action,
                    }).encode()
                ),
                routing_key="moderation.action_taken",
            )
    except Exception as exc:
        logger.warning("Failed to publish moderation event: %s", exc)


async def _publish_chat_event(room_id: uuid.UUID, msg: ChatMessageOut) -> None:
    """Publish chat.message.sent to RabbitMQ (best-effort)."""
    import os
    try:
        import aio_pika
        conn = await aio_pika.connect_robust(
            os.environ.get("RABBITMQ_URL", "amqp://colab:colab@localhost:5672/")
        )
        async with conn:
            channel = await conn.channel()
            exchange = await channel.declare_exchange("chat", aio_pika.ExchangeType.TOPIC)
            await exchange.publish(
                aio_pika.Message(
                    body=json.dumps({
                        "event": "chat.message.sent",
                        "room_id": str(room_id),
                        "msg_id": str(msg.id),
                        "sender_profile_id": str(msg.sender_profile_id),
                        "type": msg.type,
                        "created_at": msg.created_at.isoformat(),
                    }).encode()
                ),
                routing_key="chat.message.sent",
            )
    except Exception as exc:
        logger.warning("Failed to publish chat.message.sent: %s", exc)


async def _handle_typing(
    ws: WebSocket,
    ws_id: int,
    payload: dict,
    room: ChatRoom,
    profile_id: uuid.UUID,
    presence: AsyncPresenceManager,
    conn_mgr: AsyncConnectionManager,
) -> None:
    if not _rate_check_typing(ws_id):
        return  # silently drop excess typing frames

    try:
        typing_payload = WSTypingPayload(**payload)
    except Exception:
        return

    is_typing = typing_payload.state == "start"
    await presence.set_typing(room.id, profile_id, typing=is_typing)
    # Broadcast typing to room via Redis pub/sub
    await presence.publish(room.id, ws_typing(profile_id, typing_payload.state))


async def _handle_read_ack(
    ws: WebSocket,
    ws_id: int,
    payload: dict,
    room: ChatRoom,
    profile_id: uuid.UUID,
    db: AsyncSession,
    presence: AsyncPresenceManager,
    conn_mgr: AsyncConnectionManager,
) -> None:
    if not _rate_check_read_ack(ws_id):
        return

    if room.state == "read_only":
        return  # frozen during block

    try:
        ack_payload = WSReadAckPayload(**payload)
    except Exception:
        return

    now = datetime.now(tz=timezone.utc)
    # Monotonic upsert — never move pointer backward
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
        {
            "room_id": room.id,
            "profile_id": profile_id,
            "msg_id": ack_payload.up_to_msg_id,
            "now": now,
        },
    )
    await db.commit()

    # Broadcast read event to room
    await presence.publish(room.id, ws_read(profile_id, ack_payload.up_to_msg_id, now))


async def _handle_reconnect(
    ws: WebSocket,
    ws_id: int,
    payload: dict,
    room: ChatRoom,
    profile_id: uuid.UUID,
    db: AsyncSession,
    conn_mgr: AsyncConnectionManager,
) -> None:
    if not _rate_check_reconnect(ws_id):
        await conn_mgr.send_to(
            ws, ws_error("RATE_LIMITED", "Too many reconnect frames")
        )
        return

    try:
        reconnect_payload = WSReconnectPayload(**payload)
    except Exception:
        return

    since_id = str(reconnect_payload.since_msg_id)
    page_size = _settings.replay_page_size

    # Fetch messages after since_msg_id (UUIDv7 lexicographic ordering)
    result = await db.execute(
        text("""
            SELECT id, room_id, sender_profile_id, type, body, media_key, mime,
                   size_bytes, duration_ms, reply_to, client_nonce,
                   edited_at, deleted_at, moderation_score, moderation_status, created_at
            FROM chat.chat_message
            WHERE room_id = :room_id
              AND id::text > :since_id
              AND moderation_status IN ('allowed', 'soft_warn')
              AND deleted_at IS NULL
            ORDER BY id ASC
            LIMIT :limit
        """),
        {"room_id": room.id, "since_id": since_id, "limit": page_size + 1},
    )
    rows = result.fetchall()
    has_more = len(rows) > page_size
    rows = rows[:page_size]

    messages = [
        ChatMessageOut(
            id=r.id,
            room_id=r.room_id,
            sender_profile_id=r.sender_profile_id,
            type=r.type,
            body=r.body,
            media_key=r.media_key,
            mime=r.mime,
            size_bytes=r.size_bytes,
            duration_ms=r.duration_ms,
            reply_to=r.reply_to,
            moderation_status=r.moderation_status,
            edited_at=r.edited_at,
            created_at=r.created_at,
        )
        for r in rows
    ]

    await conn_mgr.send_to(ws, ws_replay(messages, has_more))


async def handle_room_ws(
    ws: WebSocket,
    room_id: uuid.UUID,
    profile_id: uuid.UUID,
    db: AsyncSession,
    presence: AsyncPresenceManager,
    conn_mgr: AsyncConnectionManager,
) -> None:
    """
    Main WebSocket connection handler.
    Manages the receive loop + Redis subscribe loop concurrently.
    """
    await ws.accept()

    # Load and validate room
    result = await db.execute(
        select(ChatRoom).where(ChatRoom.id == room_id)
    )
    room = result.scalar_one_or_none()
    if not room or profile_id not in room.participant_ids:
        await ws.send_text(json.dumps(ws_error("ROOM_NOT_FOUND", "Room not found or access denied")))
        await ws.close(code=4003)
        return

    ws_id = id(ws)
    conn_mgr.add(room_id, ws)

    # Mark online
    await presence.set_online(room_id, profile_id, online=True)

    # Subscribe to Redis channel for this room
    pubsub = await presence.subscribe(room_id)

    connection_start = time.monotonic()

    async def _redis_listener() -> None:
        """Forward messages from Redis pub/sub to local WS connections."""
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        envelope = json.loads(message["data"])
                    except Exception:
                        continue
                    await conn_mgr.local_broadcast(room_id, envelope)
        except Exception as exc:
            logger.debug("Redis listener error: %s", exc)

    async def _expiry_watcher() -> None:
        """Send connection_expiry_warning 5 min before the 2-hour API GW limit."""
        target = _settings.expiry_warning_at_seconds
        await asyncio.sleep(target)
        remaining = _settings.connection_expiry_seconds - target
        await conn_mgr.send_to(ws, ws_connection_expiry_warning(remaining))

    listener_task = asyncio.ensure_future(_redis_listener())
    expiry_task = asyncio.ensure_future(_expiry_watcher())

    try:
        while True:
            raw = await ws.receive_text()

            # Refresh presence TTL on every frame
            await presence.refresh_ttl(room_id, profile_id)

            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                await conn_mgr.send_to(
                    ws, ws_error("INTERNAL_ERROR", "Invalid JSON frame")
                )
                continue

            msg_type = frame.get("type", "")
            payload = frame.get("payload", {})
            request_id = frame.get("request_id")

            if msg_type == "send":
                await _handle_send(
                    ws, ws_id, payload, room, profile_id, db, presence, conn_mgr, request_id
                )
            elif msg_type == "typing":
                await _handle_typing(ws, ws_id, payload, room, profile_id, presence, conn_mgr)
            elif msg_type == "read_ack":
                await _handle_read_ack(
                    ws, ws_id, payload, room, profile_id, db, presence, conn_mgr
                )
            elif msg_type == "ping":
                await conn_mgr.send_to(ws, ws_pong())
            elif msg_type == "reconnect":
                await _handle_reconnect(ws, ws_id, payload, room, profile_id, db, conn_mgr)
            else:
                await conn_mgr.send_to(
                    ws, ws_error("INTERNAL_ERROR", f"Unknown frame type: {msg_type}")
                )

            # Re-fetch room state in case it changed (e.g., block event)
            await db.refresh(room)

    except WebSocketDisconnect:
        logger.info("WS disconnected: profile=%s room=%s", profile_id, room_id)
    except Exception as exc:
        logger.error("WS error: %s", exc, exc_info=True)
    finally:
        listener_task.cancel()
        expiry_task.cancel()
        conn_mgr.remove(room_id, ws)
        await presence.set_online(room_id, profile_id, online=False)
        await presence.unsubscribe(pubsub, room_id)
        _rate_counters.pop(ws_id, None)
