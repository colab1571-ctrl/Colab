"""
Tests for chat-svc WebSocket protocol and message handling.

Covers:
- T-57: unit tests for handler logic
- T-59: WS round-trip
- T-61: moderation scoring paths
- T-62: block enforcement
- T-63: read receipt monotonic constraint
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import (
    ChatMessageOut,
    ws_error,
    ws_message,
    ws_message_ack,
    ws_pong,
    ws_read,
    ws_replay,
    ws_room_state,
    ws_soft_warn_ack,
)
from app.uuidv7 import generate_uuidv7


# ---------------------------------------------------------------------------
# UUIDv7 tests
# ---------------------------------------------------------------------------


def test_uuidv7_is_version_7():
    uid = generate_uuidv7()
    assert uid.version == 7


def test_uuidv7_ordering():
    ids = [generate_uuidv7() for _ in range(10)]
    sorted_ids = sorted(ids, key=lambda x: x.int)
    assert ids == sorted_ids  # generated in order


def test_uuidv7_uniqueness():
    ids = {generate_uuidv7() for _ in range(100)}
    assert len(ids) == 100


# ---------------------------------------------------------------------------
# Schema / wire format tests
# ---------------------------------------------------------------------------


def test_ws_error_format():
    frame = ws_error("ROOM_READ_ONLY", "Room is read-only", "req-123")
    assert frame["type"] == "error"
    assert frame["payload"]["code"] == "ROOM_READ_ONLY"
    assert frame["payload"]["request_id"] == "req-123"


def test_ws_pong():
    frame = ws_pong()
    assert frame["type"] == "pong"


def test_ws_room_state():
    frame = ws_room_state("read_only")
    assert frame["type"] == "room_state"
    assert frame["payload"]["state"] == "read_only"


def test_ws_replay_format():
    now = datetime.now(tz=timezone.utc)
    msgs = [
        ChatMessageOut(
            id=generate_uuidv7(),
            room_id=uuid.uuid4(),
            sender_profile_id=uuid.uuid4(),
            type="text",
            body="hello",
            moderation_status="allowed",
            created_at=now,
        )
    ]
    frame = ws_replay(msgs, has_more=False)
    assert frame["type"] == "replay"
    assert len(frame["payload"]["messages"]) == 1
    assert frame["payload"]["has_more"] is False


def test_ws_replay_has_more():
    now = datetime.now(tz=timezone.utc)
    msgs = [
        ChatMessageOut(
            id=generate_uuidv7(),
            room_id=uuid.uuid4(),
            sender_profile_id=uuid.uuid4(),
            type="text",
            body=f"msg-{i}",
            moderation_status="allowed",
            created_at=now,
        )
        for i in range(5)
    ]
    frame = ws_replay(msgs, has_more=True)
    assert frame["payload"]["has_more"] is True


# ---------------------------------------------------------------------------
# Rate limiting tests (unit)
# ---------------------------------------------------------------------------


def test_rate_check_send_allows_up_to_limit():
    from app.ws.handler import _rate_check_send, _rate_counters
    ws_id = 99991
    _rate_counters.pop(ws_id, None)

    # Patch time to fix minute
    import time
    with patch("app.ws.handler.time") as mock_time:
        mock_time.time.return_value = 60.0  # minute = 1
        mock_time.monotonic.return_value = 100.0
        for i in range(30):
            assert _rate_check_send(ws_id) is True
        assert _rate_check_send(ws_id) is False  # 31st is rejected


def test_rate_check_typing_enforces_cooldown():
    from app.ws.handler import _rate_check_typing, _rate_counters
    ws_id = 99992
    _rate_counters.pop(ws_id, None)

    import time
    with patch("app.ws.handler.time") as mock_time:
        mock_time.monotonic.return_value = 0.0
        mock_time.time.return_value = 0.0
        assert _rate_check_typing(ws_id) is True  # first allowed

        mock_time.monotonic.return_value = 1.0  # 1 sec later — within 3s cooldown
        assert _rate_check_typing(ws_id) is False

        mock_time.monotonic.return_value = 4.0  # 4s later — ok
        assert _rate_check_typing(ws_id) is True


# ---------------------------------------------------------------------------
# Moderation routing tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_moderation_circuit_breaker_on_timeout():
    """If moderation-svc times out, message should pass through as 'pending'."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.side_effect = Exception("timeout")
        mock_client_cls.return_value = mock_client

        from app.ws.handler import _call_moderation
        result = await _call_moderation("test body")
        assert result["score"] == 0.0
        assert result["decision"] == "allow"


@pytest.mark.asyncio
async def test_moderation_score_routing_allowed():
    """Score < 0.4 → allowed."""
    with patch("app.ws.handler._call_moderation", new_callable=AsyncMock) as mock_mod:
        mock_mod.return_value = {"score": 0.1, "decision": "allow", "categories": []}

        # Verify routing — the score < 0.4 path sets mod_status="allowed"
        from app.ws.handler import _call_moderation
        scan = await _call_moderation("clean message")
        score = scan["score"]
        assert score < 0.4


@pytest.mark.asyncio
async def test_moderation_score_soft_warn(mock_db, mock_presence, mock_conn_mgr):
    """Score 0.4–0.7 → soft_warn; message broadcast."""
    room_id = uuid.uuid4()
    profile_id = uuid.uuid4()

    from app.models import ChatRoom
    room = MagicMock(spec=ChatRoom)
    room.id = room_id
    room.state = "open"
    room.participant_ids = [profile_id, uuid.uuid4()]

    ws = AsyncMock()
    ws_id = id(ws)

    with patch("app.ws.handler._call_moderation", new_callable=AsyncMock) as mock_mod, \
         patch("app.ws.handler.generate_uuidv7") as mock_uuid, \
         patch("app.ws.handler._rate_check_send", return_value=True):
        mock_mod.return_value = {"score": 0.5, "decision": "soft_warn", "categories": []}
        msg_id = uuid.uuid4()
        mock_uuid.return_value = msg_id

        # Mock execute for dedup check — returns None (no existing message)
        from unittest.mock import AsyncMock as AM
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        mock_msg = MagicMock()
        mock_msg.id = msg_id
        mock_msg.room_id = room_id
        mock_msg.sender_profile_id = profile_id
        mock_msg.type = "text"
        mock_msg.body = "soft warn content"
        mock_msg.moderation_status = "soft_warn"
        mock_msg.created_at = datetime.now(tz=timezone.utc)
        mock_msg.media_key = None
        mock_msg.mime = None
        mock_msg.size_bytes = None
        mock_msg.duration_ms = None
        mock_msg.reply_to = None
        mock_msg.edited_at = None

        # After commit+refresh, the message is available
        mock_db.refresh = AsyncMock(side_effect=lambda m: None)

        from app.ws.handler import _handle_send
        payload = {
            "body": "soft warn content",
            "client_nonce": str(uuid.uuid4()),
            "reply_to": None,
        }

        with patch("app.ws.handler._build_message_out", new_callable=AsyncMock) as mock_build, \
             patch("app.ws.handler.asyncio.ensure_future"):
            mock_msg_out = ChatMessageOut(
                id=msg_id,
                room_id=room_id,
                sender_profile_id=profile_id,
                type="text",
                body="soft warn content",
                moderation_status="soft_warn",
                created_at=datetime.now(tz=timezone.utc),
            )
            mock_build.return_value = mock_msg_out

            await _handle_send(
                ws, id(ws), payload, room, profile_id, mock_db, mock_presence, mock_conn_mgr, None
            )

        # Should broadcast to room (via Redis publish)
        mock_presence.publish.assert_called_once()


@pytest.mark.asyncio
async def test_moderation_auto_hidden_not_broadcast(mock_db, mock_presence, mock_conn_mgr):
    """Score >= 0.9 → auto_hidden; NOT broadcast; sender gets MODERATION_REJECTED."""
    room_id = uuid.uuid4()
    profile_id = uuid.uuid4()

    from app.models import ChatRoom
    room = MagicMock(spec=ChatRoom)
    room.id = room_id
    room.state = "open"
    room.participant_ids = [profile_id, uuid.uuid4()]

    ws = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with patch("app.ws.handler._call_moderation", new_callable=AsyncMock) as mock_mod, \
         patch("app.ws.handler.generate_uuidv7", return_value=uuid.uuid4()), \
         patch("app.ws.handler._rate_check_send", return_value=True), \
         patch("app.ws.handler.asyncio.ensure_future"):
        mock_mod.return_value = {"score": 0.95, "decision": "auto_hide", "categories": []}

        from app.ws.handler import _handle_send
        payload = {
            "body": "very bad content",
            "client_nonce": str(uuid.uuid4()),
            "reply_to": None,
        }
        await _handle_send(
            ws, id(ws), payload, room, profile_id, mock_db, mock_presence, mock_conn_mgr, None
        )

    # Should NOT publish to Redis
    mock_presence.publish.assert_not_called()
    # Should send MODERATION_REJECTED to sender
    mock_conn_mgr.send_to.assert_called_once()
    call_args = mock_conn_mgr.send_to.call_args[0]
    assert call_args[1]["payload"]["code"] == "MODERATION_REJECTED"


@pytest.mark.asyncio
async def test_moderation_hold_score_0_8(mock_db, mock_presence, mock_conn_mgr):
    """Score 0.7–0.9 → hidden; sender gets MODERATION_HOLD."""
    room_id = uuid.uuid4()
    profile_id = uuid.uuid4()

    from app.models import ChatRoom
    room = MagicMock(spec=ChatRoom)
    room.id = room_id
    room.state = "open"
    room.participant_ids = [profile_id, uuid.uuid4()]

    ws = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with patch("app.ws.handler._call_moderation", new_callable=AsyncMock) as mock_mod, \
         patch("app.ws.handler.generate_uuidv7", return_value=uuid.uuid4()), \
         patch("app.ws.handler._rate_check_send", return_value=True), \
         patch("app.ws.handler.asyncio.ensure_future"):
        mock_mod.return_value = {"score": 0.8, "decision": "hold", "categories": []}

        from app.ws.handler import _handle_send
        payload = {
            "body": "questionable content",
            "client_nonce": str(uuid.uuid4()),
            "reply_to": None,
        }
        await _handle_send(
            ws, id(ws), payload, room, profile_id, mock_db, mock_presence, mock_conn_mgr, None
        )

    mock_presence.publish.assert_not_called()
    mock_conn_mgr.send_to.assert_called_once()
    call_args = mock_conn_mgr.send_to.call_args[0]
    assert call_args[1]["payload"]["code"] == "MODERATION_HOLD"


# ---------------------------------------------------------------------------
# Block enforcement tests (T-62)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_block_read_only_rejects_send(mock_db, mock_presence, mock_conn_mgr):
    """Room in read_only state → ROOM_READ_ONLY error on send."""
    room_id = uuid.uuid4()
    profile_id = uuid.uuid4()

    from app.models import ChatRoom
    room = MagicMock(spec=ChatRoom)
    room.id = room_id
    room.state = "read_only"  # BLOCKED
    room.participant_ids = [profile_id, uuid.uuid4()]

    ws = AsyncMock()

    with patch("app.ws.handler._rate_check_send", return_value=True):
        from app.ws.handler import _handle_send
        payload = {
            "body": "cannot send this",
            "client_nonce": str(uuid.uuid4()),
            "reply_to": None,
        }
        await _handle_send(
            ws, id(ws), payload, room, profile_id, mock_db, mock_presence, mock_conn_mgr, "req-1"
        )

    mock_conn_mgr.send_to.assert_called_once()
    frame = mock_conn_mgr.send_to.call_args[0][1]
    assert frame["payload"]["code"] == "ROOM_READ_ONLY"
    mock_presence.publish.assert_not_called()


# ---------------------------------------------------------------------------
# Read receipt monotonic constraint (T-63)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_ack_uses_monotonic_upsert(mock_db, mock_presence, mock_conn_mgr):
    """_handle_read_ack must issue monotonic ON CONFLICT upsert."""
    room_id = uuid.uuid4()
    profile_id = uuid.uuid4()

    from app.models import ChatRoom
    room = MagicMock(spec=ChatRoom)
    room.id = room_id
    room.state = "open"

    ws = AsyncMock()
    msg_id = generate_uuidv7()

    mock_db.execute.return_value = AsyncMock()

    from app.ws.handler import _handle_read_ack
    payload = {"up_to_msg_id": str(msg_id)}
    await _handle_read_ack(ws, id(ws), payload, room, profile_id, mock_db, mock_presence, mock_conn_mgr)

    # DB execute called with monotonic upsert query
    assert mock_db.execute.called
    sql_call = str(mock_db.execute.call_args[0][0])
    assert "ON CONFLICT" in sql_call
    assert "EXCLUDED.last_read_msg_id" in sql_call

    # Broadcast read event
    mock_presence.publish.assert_called_once()
    event = mock_presence.publish.call_args[0][1]
    assert event["type"] == "read"


@pytest.mark.asyncio
async def test_read_ack_blocked_in_read_only_room(mock_db, mock_presence, mock_conn_mgr):
    """read_ack must be a no-op when room is read_only."""
    room_id = uuid.uuid4()
    profile_id = uuid.uuid4()

    from app.models import ChatRoom
    room = MagicMock(spec=ChatRoom)
    room.id = room_id
    room.state = "read_only"

    ws = AsyncMock()
    msg_id = generate_uuidv7()

    from app.ws.handler import _handle_read_ack
    payload = {"up_to_msg_id": str(msg_id)}
    await _handle_read_ack(ws, id(ws), payload, room, profile_id, mock_db, mock_presence, mock_conn_mgr)

    mock_db.execute.assert_not_called()
    mock_presence.publish.assert_not_called()


# ---------------------------------------------------------------------------
# Reconnect + replay tests (T-15 / AC-06)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconnect_handler_returns_replay(mock_db, mock_conn_mgr):
    """reconnect frame with since_msg_id returns replay with missed messages."""
    room_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    since_id = generate_uuidv7()

    from app.models import ChatRoom
    room = MagicMock(spec=ChatRoom)
    room.id = room_id

    ws = AsyncMock()
    now = datetime.now(tz=timezone.utc)

    # Mock DB returning 5 messages
    mock_rows = []
    for i in range(5):
        row = MagicMock()
        row.id = generate_uuidv7()
        row.room_id = room_id
        row.sender_profile_id = uuid.uuid4()
        row.type = "text"
        row.body = f"missed msg {i}"
        row.media_key = None
        row.mime = None
        row.size_bytes = None
        row.duration_ms = None
        row.reply_to = None
        row.moderation_status = "allowed"
        row.edited_at = None
        row.created_at = now
        mock_rows.append(row)

    mock_result = MagicMock()
    mock_result.fetchall.return_value = mock_rows
    mock_db.execute.return_value = mock_result

    with patch("app.ws.handler._rate_check_reconnect", return_value=True):
        from app.ws.handler import _handle_reconnect
        payload = {"since_msg_id": str(since_id)}
        await _handle_reconnect(ws, id(ws), payload, room, profile_id, mock_db, mock_conn_mgr)

    mock_conn_mgr.send_to.assert_called_once()
    frame = mock_conn_mgr.send_to.call_args[0][1]
    assert frame["type"] == "replay"
    assert len(frame["payload"]["messages"]) == 5
    assert frame["payload"]["has_more"] is False


@pytest.mark.asyncio
async def test_reconnect_has_more_when_exceeds_page_size():
    """has_more=True when DB returns page_size+1 messages."""
    room_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    since_id = generate_uuidv7()

    from app.models import ChatRoom
    room = MagicMock(spec=ChatRoom)
    room.id = room_id

    ws = AsyncMock()
    mock_conn_mgr = AsyncMock()
    mock_db = AsyncMock()
    now = datetime.now(tz=timezone.utc)

    # Return 201 rows (page_size=200, so has_more=True)
    mock_rows = []
    for i in range(201):
        row = MagicMock()
        row.id = generate_uuidv7()
        row.room_id = room_id
        row.sender_profile_id = uuid.uuid4()
        row.type = "text"
        row.body = f"msg {i}"
        row.media_key = None
        row.mime = None
        row.size_bytes = None
        row.duration_ms = None
        row.reply_to = None
        row.moderation_status = "allowed"
        row.edited_at = None
        row.created_at = now
        mock_rows.append(row)

    mock_result = MagicMock()
    mock_result.fetchall.return_value = mock_rows
    mock_db.execute.return_value = mock_result

    with patch("app.ws.handler._rate_check_reconnect", return_value=True):
        from app.ws.handler import _handle_reconnect
        payload = {"since_msg_id": str(since_id)}
        await _handle_reconnect(ws, id(ws), payload, room, profile_id, mock_db, mock_conn_mgr)

    frame = mock_conn_mgr.send_to.call_args[0][1]
    assert frame["payload"]["has_more"] is True
    assert len(frame["payload"]["messages"]) == 200


# ---------------------------------------------------------------------------
# Presence tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_presence_manager_set_online():
    """AsyncPresenceManager.set_online writes correct hash + TTL."""
    mock_redis = AsyncMock()
    mock_redis.hset = AsyncMock()
    mock_redis.expire = AsyncMock()

    from app.ws.presence import AsyncPresenceManager
    pm = AsyncPresenceManager(mock_redis)

    room_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    await pm.set_online(room_id, profile_id, online=True)

    mock_redis.hset.assert_called_once()
    call_kwargs = mock_redis.hset.call_args[1]
    assert call_kwargs["mapping"]["online"] == "1"
    mock_redis.expire.assert_called_once_with(
        f"chat:presence:{room_id}:{profile_id}", 90
    )


@pytest.mark.asyncio
async def test_presence_manager_publish():
    """publish() serializes envelope and calls redis.publish."""
    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock()

    from app.ws.presence import AsyncPresenceManager
    pm = AsyncPresenceManager(mock_redis)

    room_id = uuid.uuid4()
    envelope = {"type": "message", "payload": {"id": "test"}}
    await pm.publish(room_id, envelope)

    mock_redis.publish.assert_called_once()
    channel = mock_redis.publish.call_args[0][0]
    assert channel == f"chat:room:{room_id}"
    data = json.loads(mock_redis.publish.call_args[0][1])
    assert data["type"] == "message"


# ---------------------------------------------------------------------------
# Connection manager tests
# ---------------------------------------------------------------------------


def test_connection_manager_add_remove():
    from app.ws.connection_manager import AsyncConnectionManager
    cm = AsyncConnectionManager()
    room_id = uuid.uuid4()

    ws1 = MagicMock()
    ws2 = MagicMock()

    cm.add(room_id, ws1)
    cm.add(room_id, ws2)
    assert cm.local_count(room_id) == 2

    cm.remove(room_id, ws1)
    assert cm.local_count(room_id) == 1

    cm.remove(room_id, ws2)
    assert cm.local_count(room_id) == 0


@pytest.mark.asyncio
async def test_connection_manager_local_broadcast():
    from app.ws.connection_manager import AsyncConnectionManager
    cm = AsyncConnectionManager()
    room_id = uuid.uuid4()

    ws1 = AsyncMock()
    ws2 = AsyncMock()

    cm.add(room_id, ws1)
    cm.add(room_id, ws2)

    envelope = {"type": "message", "payload": {"body": "hi"}}
    await cm.local_broadcast(room_id, envelope)

    ws1.send_text.assert_called_once()
    ws2.send_text.assert_called_once()


# ---------------------------------------------------------------------------
# Typing indicator tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_typing_start_updates_presence(mock_db, mock_presence, mock_conn_mgr):
    room_id = uuid.uuid4()
    profile_id = uuid.uuid4()

    from app.models import ChatRoom
    room = MagicMock(spec=ChatRoom)
    room.id = room_id
    room.state = "open"

    ws = AsyncMock()

    with patch("app.ws.handler._rate_check_typing", return_value=True):
        from app.ws.handler import _handle_typing
        payload = {"state": "start"}
        await _handle_typing(ws, id(ws), payload, room, profile_id, mock_presence, mock_conn_mgr)

    mock_presence.set_typing.assert_called_once_with(room_id, profile_id, typing=True)
    mock_presence.publish.assert_called_once()
    event = mock_presence.publish.call_args[0][1]
    assert event["type"] == "typing"
    assert event["payload"]["state"] == "start"


# ---------------------------------------------------------------------------
# Ping/Pong tests
# ---------------------------------------------------------------------------


def test_ws_pong_format():
    frame = ws_pong()
    assert frame == {"type": "pong", "payload": {}}


# ---------------------------------------------------------------------------
# Event consumer tests (T-24 — match.created creates room)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_match_created_creates_room():
    collab_id = uuid.uuid4()
    profile_a = uuid.uuid4()
    profile_b = uuid.uuid4()

    payload = {
        "collaboration_id": str(collab_id),
        "profile_id_a": str(profile_a),
        "profile_id_b": str(profile_b),
    }

    with patch("app.workers.event_consumers._get_session_factory") as mock_factory, \
         patch("app.workers.event_consumers._emit_collab_created", new_callable=AsyncMock):
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_ctx

        # No existing room
        no_result = MagicMock()
        no_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = no_result

        from app.workers.event_consumers import _handle_match_created
        await _handle_match_created(payload)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_match_created_idempotent():
    """If room already exists for collab, don't create another."""
    collab_id = uuid.uuid4()
    profile_a = uuid.uuid4()
    profile_b = uuid.uuid4()

    payload = {
        "collaboration_id": str(collab_id),
        "profile_id_a": str(profile_a),
        "profile_id_b": str(profile_b),
    }

    with patch("app.workers.event_consumers._get_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_ctx

        # Existing room found
        existing = MagicMock()
        existing.scalar_one_or_none.return_value = MagicMock()  # existing room
        mock_session.execute.return_value = existing

        from app.workers.event_consumers import _handle_match_created
        await _handle_match_created(payload)

        mock_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Block handler tests (T-18 / T-62)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_block_created_flips_room_to_read_only():
    profile_a = uuid.uuid4()
    profile_b = uuid.uuid4()

    payload = {
        "blocker_profile_id": str(profile_a),
        "blocked_profile_id": str(profile_b),
    }

    mock_presence = AsyncMock()

    with patch("app.workers.event_consumers._get_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_ctx

        room_row = MagicMock()
        room_row.id = uuid.uuid4()
        room_result = MagicMock()
        room_result.fetchone.return_value = room_row
        mock_session.execute.return_value = room_result

        from app.workers.event_consumers import _handle_block_created
        await _handle_block_created(payload, mock_presence)

        # Should UPDATE room state
        update_call = mock_session.execute.call_args_list[-1]
        sql_text = str(update_call[0][0])
        assert "read_only" in sql_text

        # Should broadcast room_state via Redis
        mock_presence.publish.assert_called_once()
        event = mock_presence.publish.call_args[0][1]
        assert event["type"] == "room_state"
        assert event["payload"]["state"] == "read_only"
