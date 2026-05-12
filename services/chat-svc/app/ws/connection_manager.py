"""
chat-svc — AsyncConnectionManager

In-process registry of WebSocket connections keyed by room_id.
Cross-pod fanout is handled via Redis pub/sub in presence.py.

Each pod maintains:
  _connections: dict[room_id, set[WebSocket]]

On publish from Redis channel, the listener task calls `local_broadcast`,
which sends to all local connections in that room.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class AsyncConnectionManager:
    """Manages per-room WebSocket connection pools on this pod."""

    def __init__(self) -> None:
        # room_id (str) → set of WebSocket objects
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        # ws → room_id mapping for cleanup
        self._ws_room: dict[int, str] = {}

    def add(self, room_id: uuid.UUID, ws: WebSocket) -> None:
        rid = str(room_id)
        self._connections[rid].add(ws)
        self._ws_room[id(ws)] = rid

    def remove(self, room_id: uuid.UUID, ws: WebSocket) -> None:
        rid = str(room_id)
        self._connections[rid].discard(ws)
        self._ws_room.pop(id(ws), None)
        if not self._connections[rid]:
            del self._connections[rid]

    def local_count(self, room_id: uuid.UUID) -> int:
        return len(self._connections.get(str(room_id), set()))

    async def local_broadcast(
        self, room_id: uuid.UUID, envelope: dict[str, Any]
    ) -> None:
        """Send envelope to all local connections in room."""
        rid = str(room_id)
        connections = self._connections.get(rid, set()).copy()
        if not connections:
            return

        text = json.dumps(envelope)
        tasks = [ws.send_text(text) for ws in connections]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for ws, result in zip(connections, results):
            if isinstance(result, Exception):
                logger.debug("WS send error (likely closed): %s", result)

    async def send_to(self, ws: WebSocket, envelope: dict[str, Any]) -> None:
        """Send envelope to a single WebSocket connection."""
        try:
            await ws.send_text(json.dumps(envelope))
        except Exception as exc:
            logger.debug("WS send_to error: %s", exc)
