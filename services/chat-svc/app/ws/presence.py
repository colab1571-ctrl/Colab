"""
chat-svc — AsyncPresenceManager

Redis key layout:
  chat:presence:{room_id}:{profile_id}  →  Hash { online, typing, last_seen_at }
  TTL: 90 s (reset on any frame from client)

Pub/sub channel: chat:room:{room_id}
  Publishes full server→client JSON envelopes.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

import redis.asyncio as aioredis

from app.config import get_chat_settings


class AsyncPresenceManager:
    """Manages presence state in Redis and pub/sub fanout."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client
        self._settings = get_chat_settings()

    # ------------------------------------------------------------------
    # Presence helpers
    # ------------------------------------------------------------------

    def _presence_key(self, room_id: uuid.UUID, profile_id: uuid.UUID) -> str:
        return f"chat:presence:{room_id}:{profile_id}"

    def _channel(self, room_id: uuid.UUID) -> str:
        return f"chat:room:{room_id}"

    async def set_online(
        self, room_id: uuid.UUID, profile_id: uuid.UUID, *, online: bool = True
    ) -> None:
        key = self._presence_key(room_id, profile_id)
        now = datetime.now(tz=timezone.utc).isoformat()
        await self._redis.hset(
            key,
            mapping={"online": "1" if online else "0", "last_seen_at": now},
        )
        if online:
            await self._redis.expire(key, self._settings.presence_ttl_seconds)

    async def set_typing(
        self, room_id: uuid.UUID, profile_id: uuid.UUID, *, typing: bool
    ) -> None:
        key = self._presence_key(room_id, profile_id)
        await self._redis.hset(key, "typing", "1" if typing else "0")
        await self._redis.expire(key, self._settings.presence_ttl_seconds)

    async def refresh_ttl(self, room_id: uuid.UUID, profile_id: uuid.UUID) -> None:
        key = self._presence_key(room_id, profile_id)
        await self._redis.expire(key, self._settings.presence_ttl_seconds)

    async def get_presence(
        self, room_id: uuid.UUID, profile_id: uuid.UUID
    ) -> dict:
        key = self._presence_key(room_id, profile_id)
        data = await self._redis.hgetall(key)
        return {
            "online": data.get("online", "0") == "1",
            "typing": data.get("typing", "0") == "1",
            "last_seen_at": data.get("last_seen_at", ""),
        }

    # ------------------------------------------------------------------
    # Pub/sub
    # ------------------------------------------------------------------

    async def publish(self, room_id: uuid.UUID, envelope: dict) -> None:
        """Publish a WS envelope to all pods subscribed to this room."""
        channel = self._channel(room_id)
        await self._redis.publish(channel, json.dumps(envelope))

    async def subscribe(self, room_id: uuid.UUID) -> aioredis.client.PubSub:
        """Return a PubSub object subscribed to the room channel."""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._channel(room_id))
        return pubsub

    async def unsubscribe(self, pubsub: aioredis.client.PubSub, room_id: uuid.UUID) -> None:
        await pubsub.unsubscribe(self._channel(room_id))
        await pubsub.aclose()
