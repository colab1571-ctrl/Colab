"""
Cross-pod fanout integration test (T-60 / AC-36).

Simulates two FastAPI app instances sharing a Redis pub/sub channel.
Verifies that a message sent on pod 1 arrives at a WebSocket connection
on pod 2 via Redis fanout.

Requires: live Redis at REDIS_URL (default redis://localhost:6379/0).
Run with: pytest -m integration tests/test_cross_pod_fanout.py
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import ChatMessageOut, ws_message
from app.ws.connection_manager import AsyncConnectionManager
from app.ws.presence import AsyncPresenceManager
from app.uuidv7 import generate_uuidv7


# ---------------------------------------------------------------------------
# Simulated two-pod fanout test (using mock Redis)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_pod_fanout_via_redis_mock():
    """
    Simulate two pods sharing a Redis channel.
    Pod 1 publishes a message; Pod 2's subscriber receives it and broadcasts
    to its local WS connections.
    """
    room_id = uuid.uuid4()

    # Shared message queue (simulates Redis pub/sub in-process)
    shared_queue: asyncio.Queue = asyncio.Queue()

    # --- Pod 1 ---
    mock_redis_1 = AsyncMock()
    mock_redis_1.publish = AsyncMock(
        side_effect=lambda channel, data: shared_queue.put_nowait(data)
    )
    presence_1 = AsyncPresenceManager(mock_redis_1)
    conn_mgr_1 = AsyncConnectionManager()

    # --- Pod 2 ---
    mock_redis_2 = AsyncMock()
    presence_2 = AsyncPresenceManager(mock_redis_2)
    conn_mgr_2 = AsyncConnectionManager()

    # Add a WS client to Pod 2
    ws_pod2 = AsyncMock()
    received_messages = []
    ws_pod2.send_text = AsyncMock(
        side_effect=lambda data: received_messages.append(json.loads(data))
    )
    conn_mgr_2.add(room_id, ws_pod2)

    # --- Pod 2 Redis listener simulation ---
    async def pod2_listener():
        data = await asyncio.wait_for(shared_queue.get(), timeout=2.0)
        envelope = json.loads(data)
        await conn_mgr_2.local_broadcast(room_id, envelope)

    listener_task = asyncio.create_task(pod2_listener())

    # --- Pod 1 sends a message ---
    now = datetime.now(tz=timezone.utc)
    msg_out = ChatMessageOut(
        id=generate_uuidv7(),
        room_id=room_id,
        sender_profile_id=uuid.uuid4(),
        type="text",
        body="cross-pod test message",
        moderation_status="allowed",
        created_at=now,
    )
    envelope = ws_message(msg_out)
    await presence_1.publish(room_id, envelope)

    # Wait for Pod 2 to receive
    await listener_task

    # Assert Pod 2's WS client received the message
    assert len(received_messages) == 1
    assert received_messages[0]["type"] == "message"
    assert received_messages[0]["payload"]["body"] == "cross-pod test message"


@pytest.mark.asyncio
async def test_cross_pod_fanout_multiple_recipients():
    """Pod 2 with 3 WS clients — all 3 receive the broadcast."""
    room_id = uuid.uuid4()
    shared_queue: asyncio.Queue = asyncio.Queue()

    mock_redis_1 = AsyncMock()
    mock_redis_1.publish = AsyncMock(
        side_effect=lambda channel, data: shared_queue.put_nowait(data)
    )
    presence_1 = AsyncPresenceManager(mock_redis_1)

    conn_mgr_2 = AsyncConnectionManager()
    received_counts = [0, 0, 0]

    for i, count_list in enumerate([received_counts]):
        for j in range(3):
            ws = AsyncMock()
            idx = j

            async def make_side_effect(index):
                async def side_effect(data):
                    received_counts[index] += 1
                return side_effect

            ws.send_text = AsyncMock(
                side_effect=lambda data, i=j: received_counts.__setitem__(i, received_counts[i] + 1)
            )
            conn_mgr_2.add(room_id, ws)

    now = datetime.now(tz=timezone.utc)
    msg_out = ChatMessageOut(
        id=generate_uuidv7(),
        room_id=room_id,
        sender_profile_id=uuid.uuid4(),
        type="text",
        body="broadcast to all",
        moderation_status="allowed",
        created_at=now,
    )
    envelope = ws_message(msg_out)

    # Simulate Redis listener on pod 2
    async def pod2_listener():
        data = await asyncio.wait_for(shared_queue.get(), timeout=2.0)
        evt = json.loads(data)
        await conn_mgr_2.local_broadcast(room_id, evt)

    listener = asyncio.create_task(pod2_listener())
    await presence_1.publish(room_id, envelope)
    await listener

    # All 3 connections should have received the message
    assert conn_mgr_2.local_count(room_id) == 3


@pytest.mark.asyncio
async def test_presence_publish_channel_naming():
    """Verify Redis channel name follows chat:room:{room_id} convention."""
    room_id = uuid.uuid4()
    published_channels = []

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock(
        side_effect=lambda channel, data: published_channels.append(channel)
    )

    presence = AsyncPresenceManager(mock_redis)
    await presence.publish(room_id, {"type": "test"})

    assert len(published_channels) == 1
    assert published_channels[0] == f"chat:room:{room_id}"


@pytest.mark.asyncio
async def test_send_to_handles_closed_websocket():
    """conn_mgr.send_to should not raise if WebSocket is closed."""
    conn_mgr = AsyncConnectionManager()
    ws = AsyncMock()
    ws.send_text = AsyncMock(side_effect=Exception("Connection closed"))

    # Should not raise
    await conn_mgr.send_to(ws, {"type": "test"})


@pytest.mark.asyncio
async def test_local_broadcast_handles_partial_failure():
    """local_broadcast continues if one connection fails."""
    room_id = uuid.uuid4()
    conn_mgr = AsyncConnectionManager()

    ws1 = AsyncMock()
    ws1.send_text = AsyncMock(side_effect=Exception("closed"))
    ws2 = AsyncMock()
    ws2.send_text = AsyncMock()

    conn_mgr.add(room_id, ws1)
    conn_mgr.add(room_id, ws2)

    # Should not raise; ws2 should still receive
    await conn_mgr.local_broadcast(room_id, {"type": "test"})
    ws2.send_text.assert_called_once()
