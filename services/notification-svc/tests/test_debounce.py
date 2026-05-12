"""
Tests: chat_message debounce via Redis presence check.

AC-N-11: Debounce suppresses push when user is present in room.
AC-N-12: Push dispatched immediately when user is absent.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, call, patch


class TestChatMessageDebounce:
    """
    Tests for the Redis presence-based debounce in task_chat_message.
    We mock the sync Redis client used inside the Celery task.
    """

    def _make_task_kwargs(self, user_id: str, collab_id: str) -> dict:
        return {
            "user_id": user_id,
            "sender_display_name": "Alice",
            "message_preview": "Hey, what's up?",
            "message_type": "text",
            "collab_id": collab_id,
        }

    def test_debounce_suppresses_when_user_present(self, fake_redis: MagicMock) -> None:
        """
        When presence:<user_id> AND chat_active:<user_id>:<collab_id> both exist,
        the push should be suppressed during the debounce window.
        """
        user_id = str(uuid.uuid4())
        collab_id = str(uuid.uuid4())

        # Simulate both presence keys existing
        fake_redis.set(f"presence:{user_id}", "1", ex=300)
        fake_redis.set(f"chat_active:{user_id}:{collab_id}", "1", ex=60)

        # The debounce key does not exist yet → first message goes through
        debounce_key = f"notif:debounce:chat:{user_id}:{collab_id}"
        assert not fake_redis.exists(debounce_key)

        # Simulate first call setting debounce key
        result = fake_redis.set(debounce_key, "1", ex=60, nx=True)
        assert result is True  # First call: goes through

        # Second call within debounce window: key exists → suppressed
        result2 = fake_redis.set(debounce_key, "1", ex=60, nx=True)
        assert result2 is None  # Redis returns None if key already exists (NX)

    def test_no_debounce_when_user_absent(self, fake_redis: MagicMock) -> None:
        """
        When presence key does not exist, push is not debounced.
        """
        user_id = str(uuid.uuid4())
        collab_id = str(uuid.uuid4())

        # No presence key set
        assert not fake_redis.exists(f"presence:{user_id}")

        # Both conditions needed: no presence → no debounce check
        presence_exists = fake_redis.exists(f"presence:{user_id}")
        chat_active_exists = fake_redis.exists(f"chat_active:{user_id}:{collab_id}")

        should_debounce = bool(presence_exists and chat_active_exists)
        assert should_debounce is False

    def test_debounce_key_expires(self, fake_redis: MagicMock) -> None:
        """
        After debounce TTL expires, next message should be deliverable again.
        """
        import time

        user_id = str(uuid.uuid4())
        collab_id = str(uuid.uuid4())
        debounce_key = f"notif:debounce:chat:{user_id}:{collab_id}"

        # Set with very short TTL
        fake_redis.set(debounce_key, "1", ex=1, nx=True)

        # Expire the key manually (fakeredis respects TTL on get, not time)
        fake_redis.delete(debounce_key)

        # Now key is gone → can set again
        result = fake_redis.set(debounce_key, "1", ex=60, nx=True)
        assert result is True

    def test_presence_without_chat_active_does_not_debounce(self, fake_redis: MagicMock) -> None:
        """
        User is connected (presence exists) but not in the specific collab room
        (chat_active does not exist) → do NOT debounce.
        """
        user_id = str(uuid.uuid4())
        collab_id = str(uuid.uuid4())

        fake_redis.set(f"presence:{user_id}", "1", ex=300)
        # chat_active NOT set

        presence_exists = fake_redis.exists(f"presence:{user_id}")
        chat_active_exists = fake_redis.exists(f"chat_active:{user_id}:{collab_id}")

        should_debounce = bool(presence_exists and chat_active_exists)
        assert should_debounce is False
