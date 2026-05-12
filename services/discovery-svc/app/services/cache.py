"""
discovery-svc — Redis cache layer.

Key layout per plan §8.1:
  feed:<user_id>:<mode>:<filter_hash>  Sorted Set, 30s TTL
  feed_cap:<user_id>:<YYYY-MM-DD>      String int, TTL = until UTC midnight
  feed_pref:<user_id>                  String, 7 days
  feed_keys:<user_id>                  Set (tracking active feed cache keys)
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()

_redis: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(_settings.redis_url, decode_responses=True)
    return _redis


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(tz=timezone.utc)
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    tomorrow += timedelta(days=1)
    return int((tomorrow - now).total_seconds())


# ---------------------------------------------------------------------------
# Feed preference
# ---------------------------------------------------------------------------

FEED_PREF_TTL = 7 * 86_400  # 7 days


async def get_feed_mode(user_id: str) -> str | None:
    r = get_redis()
    return await r.get(f"feed_pref:{user_id}")


async def set_feed_mode(user_id: str, mode: str) -> None:
    r = get_redis()
    await r.set(f"feed_pref:{user_id}", mode, ex=FEED_PREF_TTL)


# ---------------------------------------------------------------------------
# Daily cap
# ---------------------------------------------------------------------------

CAP_FREE = _settings.rate_limit_feed_profiles_free_per_day


async def check_and_increment_cap(
    user_id: str, tier: str, count: int
) -> tuple[bool, int]:
    """Returns (allowed, remaining). count = profiles about to be served."""
    if tier != "free":
        return True, -1  # Premium: no cap

    today = date.today().isoformat()
    key = f"feed_cap:{user_id}:{today}"
    r = get_redis()

    pipe = r.pipeline()
    pipe.incrby(key, count)
    pipe.ttl(key)
    results = await pipe.execute()
    current, ttl = results[0], results[1]

    if ttl < 0:
        await r.expire(key, _seconds_until_utc_midnight())

    if current > CAP_FREE:
        overage = current - CAP_FREE
        await r.decrby(key, overage)
        return False, 0

    return True, CAP_FREE - current


# ---------------------------------------------------------------------------
# Feed sorted set (ranked profile_id list)
# ---------------------------------------------------------------------------

FEED_TTL = 30  # seconds


def _feed_key(user_id: str, mode: str, filter_hash: str) -> str:
    return f"feed:{user_id}:{mode}:{filter_hash}"


def _feed_keys_tracker(user_id: str) -> str:
    return f"feed_keys:{user_id}"


async def get_feed_page(
    user_id: str, mode: str, filter_hash: str, offset: int, page_size: int
) -> list[str] | None:
    r = get_redis()
    key = _feed_key(user_id, mode, filter_hash)
    exists = await r.exists(key)
    if not exists:
        return None
    # ZRANGE with REV gives descending order (highest score first)
    items = await r.zrange(key, offset, offset + page_size - 1, desc=True)
    return items  # type: ignore[return-value]


async def set_feed_page(
    user_id: str, mode: str, filter_hash: str, scored_profiles: list[tuple[str, float]]
) -> None:
    """scored_profiles: [(profile_id, score), ...]"""
    r = get_redis()
    key = _feed_key(user_id, mode, filter_hash)
    tracker = _feed_keys_tracker(user_id)

    pipe = r.pipeline()
    # Add members; score as positive — we use zrange(desc=True) for descending
    for profile_id, score in scored_profiles:
        pipe.zadd(key, {profile_id: score}, nx=True)
    pipe.expire(key, FEED_TTL)
    pipe.sadd(tracker, key)
    await pipe.execute()


async def invalidate_user_feed(user_id: str) -> None:
    """Delete all feed cache keys for a user."""
    r = get_redis()
    tracker = _feed_keys_tracker(user_id)
    keys = await r.smembers(tracker)
    if keys:
        pipe = r.pipeline()
        for k in keys:
            pipe.delete(k)
        pipe.delete(tracker)
        await pipe.execute()


# ---------------------------------------------------------------------------
# Recs cache
# ---------------------------------------------------------------------------

RECS_TTL = 86_400  # 24h


async def get_recs(user_id: str) -> list[str] | None:
    r = get_redis()
    raw = await r.get(f"recs:{user_id}")
    if raw is None:
        return None
    return json.loads(raw)


async def invalidate_recs(user_id: str) -> None:
    r = get_redis()
    await r.delete(f"recs:{user_id}")
