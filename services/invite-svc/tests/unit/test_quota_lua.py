"""
Unit tests for rolling 7-day quota Lua script via fakeredis.

Covers:
  - AC-001: Free user 6th invite within 7 days → quota_exceeded (return 0)
  - AC-002: Premium user can send beyond 5 (limit=9_999_999)
  - AC-003: Rolling window resets after 7 days (old entries evicted)
  - Concurrent 6th invite: Lua atomicity prevents two concurrent 5→6 sends
"""

from __future__ import annotations

import asyncio
import time
import uuid
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
import pytest_asyncio

from app.services.quota import (
    _PREMIUM_LIMIT,
    _QUOTA_LUA,
    _WINDOW_MS,
    check_and_increment_quota,
)


@pytest_asyncio.fixture
async def redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=False)
    yield r
    await r.aclose()


async def _seed_quota(redis, user_id: uuid.UUID, count: int, age_ms: int = 0) -> None:
    """Seed `count` quota entries at `age_ms` milliseconds ago."""
    key = f"invite:quota:{user_id}"
    now_ms = int(time.time() * 1000)
    score = now_ms - age_ms
    for _ in range(count):
        invite_id = str(uuid.uuid4())
        await redis.zadd(key, {invite_id: score})
        score += 1  # slightly different scores for uniqueness


@pytest.mark.asyncio
async def test_first_five_invites_allowed(redis):
    """First 5 sends within rolling window are all allowed."""
    user_id = uuid.uuid4()

    with patch("app.services.quota._get_invite_limit", AsyncMock(return_value=5)):
        for i in range(5):
            allowed, remaining = await check_and_increment_quota(redis, user_id, uuid.uuid4())
            assert allowed, f"Send {i+1} should be allowed"

    assert remaining == 0


@pytest.mark.asyncio
async def test_sixth_invite_rejected_free_user(redis):
    """AC-001: 6th invite within 7-day window returns allowed=False."""
    user_id = uuid.uuid4()

    with patch("app.services.quota._get_invite_limit", AsyncMock(return_value=5)):
        # Send 5 invites
        for _ in range(5):
            await check_and_increment_quota(redis, user_id, uuid.uuid4())

        # 6th attempt
        allowed, remaining = await check_and_increment_quota(redis, user_id, uuid.uuid4())

    assert not allowed
    assert remaining == 0


@pytest.mark.asyncio
async def test_premium_user_unlimited(redis):
    """AC-002: Premium user (limit=9_999_999) can send 10 invites."""
    user_id = uuid.uuid4()

    with patch("app.services.quota._get_invite_limit", AsyncMock(return_value=_PREMIUM_LIMIT)):
        for i in range(10):
            allowed, remaining = await check_and_increment_quota(redis, user_id, uuid.uuid4())
            assert allowed, f"Premium send {i+1} should be allowed"


@pytest.mark.asyncio
async def test_rolling_window_evicts_old_entries(redis):
    """AC-003: After 7 days, old entries are evicted and quota resets."""
    user_id = uuid.uuid4()

    # Seed 5 invites 8 days ago (8 * 24 * 3600 * 1000 ms)
    eight_days_ms = 8 * 24 * 3600 * 1000
    await _seed_quota(redis, user_id, count=5, age_ms=eight_days_ms)

    # New send should be allowed (stale entries evicted by Lua ZREMRANGEBYSCORE)
    with patch("app.services.quota._get_invite_limit", AsyncMock(return_value=5)):
        allowed, remaining = await check_and_increment_quota(redis, user_id, uuid.uuid4())

    assert allowed, "6th send allowed after 8-day-old entries are evicted"
    assert remaining == 4  # 1 new entry, 4 slots remain


@pytest.mark.asyncio
async def test_concurrent_sixth_invite_atomicity(redis):
    """
    Lua atomicity test: two concurrent 6th-invite attempts from the same user
    should result in exactly one allowed and one rejected.

    This simulates the race condition that the Lua script prevents.
    """
    user_id = uuid.uuid4()

    # Seed 4 invites (leaving 1 slot)
    await _seed_quota(redis, user_id, count=4)

    results = []

    async def attempt():
        with patch("app.services.quota._get_invite_limit", AsyncMock(return_value=5)):
            allowed, remaining = await check_and_increment_quota(redis, user_id, uuid.uuid4())
            results.append(allowed)

    # Fire two concurrent "5th" (from 4 base) attempts
    await asyncio.gather(attempt(), attempt())

    # Exactly one should be allowed (5th slot), one rejected (6th would exceed limit)
    allowed_count = sum(results)
    assert allowed_count == 1, (
        f"Expected exactly 1 of 2 concurrent sends to succeed; got {allowed_count}"
    )


@pytest.mark.asyncio
async def test_quota_key_expires_after_7_days(redis):
    """Redis key TTL is set to 7 days on each write."""
    user_id = uuid.uuid4()

    with patch("app.services.quota._get_invite_limit", AsyncMock(return_value=5)):
        await check_and_increment_quota(redis, user_id, uuid.uuid4())

    key = f"invite:quota:{user_id}"
    ttl = await redis.ttl(key)
    # TTL should be ≤ 604800 (7 days) and > 604790 (just set)
    assert 604790 <= ttl <= 604800, f"Unexpected TTL: {ttl}"
