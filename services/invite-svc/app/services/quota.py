"""
invite-svc — Rolling 7-day invite quota via Redis Sorted Set + Lua.

Algorithm (atomic, single round-trip):
  1. ZREMRANGEBYSCORE: evict entries older than 7 days
  2. ZCARD: count remaining sends in window
  3. If count >= limit → return 0 (quota exceeded)
  4. ZADD + EXPIRE → record this send, return 1 (allowed)

Premium users receive limit=9_999_999 (effectively unlimited).
Entitlement is cached in Redis for 5 minutes per §013 NFR (<50ms).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid

import httpx
from redis.asyncio import Redis

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lua script — atomic quota check + increment
# ---------------------------------------------------------------------------

_QUOTA_LUA = """
local key    = KEYS[1]
local now    = tonumber(ARGV[1])
local cutoff = now - 604800000
local limit  = tonumber(ARGV[2])
local inv    = ARGV[3]

redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
local count = redis.call('ZCARD', key)
if count >= limit then
  return {0, count}
end
redis.call('ZADD', key, now, inv)
redis.call('EXPIRE', key, 604800)
local new_count = redis.call('ZCARD', key)
return {1, new_count}
"""

# 7-day window in milliseconds
_WINDOW_MS = 7 * 24 * 60 * 60 * 1000

# Entitlement cache TTL (5 min)
_ENT_TTL_SECONDS = 300

# Premium sentinel limit
_PREMIUM_LIMIT = 9_999_999


async def _get_invite_limit(redis: Redis, user_id: uuid.UUID) -> int:
    """
    Fetch invite-per-week entitlement, Redis-cached for 5 min.
    Falls back to free tier (5) on any error.
    """
    settings = get_settings()
    cache_key = f"entitlement:{user_id}:invites_per_week"

    cached = await redis.get(cache_key)
    if cached is not None:
        try:
            return int(cached)
        except (ValueError, TypeError):
            pass

    # Call billing-svc internal entitlements API
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(
                f"{settings.billing_svc_url}/internal/entitlements/{user_id}",
                headers={"X-Internal-Service": "invite-svc"},
            )
            if resp.status_code == 200:
                data = resp.json()
                axes: dict = data.get("axes", {})
                # axis key: "invites_per_week"; value may be int or null (unlimited)
                val = axes.get("invites_per_week")
                if val is None:
                    limit = _PREMIUM_LIMIT  # null = unlimited (premium)
                else:
                    limit = int(val)
                await redis.setex(cache_key, _ENT_TTL_SECONDS, str(limit))
                return limit
    except Exception as exc:
        logger.warning("billing-svc entitlement fetch failed for %s: %s", user_id, exc)

    # Default to free tier
    return settings.free_invite_quota_per_week


async def check_and_increment_quota(
    redis: Redis,
    user_id: uuid.UUID,
    invite_id: uuid.UUID,
) -> tuple[bool, int]:
    """
    Atomically check quota and record the send.

    Returns:
        (allowed: bool, quota_remaining: int)
    """
    settings = get_settings()
    limit = await _get_invite_limit(redis, user_id)

    key = f"invite:quota:{user_id}"
    now_ms = int(time.time() * 1000)

    result = await redis.eval(  # type: ignore[attr-defined]
        _QUOTA_LUA,
        1,
        key,
        now_ms,
        limit,
        str(invite_id),
    )

    allowed = bool(result[0])
    current_count = int(result[1])

    if allowed:
        remaining = max(0, limit - current_count) if limit < _PREMIUM_LIMIT else _PREMIUM_LIMIT
    else:
        remaining = 0

    return allowed, remaining


async def invalidate_entitlement_cache(redis: Redis, user_id: uuid.UUID) -> None:
    """Called when entitlement.changed event received."""
    key = f"entitlement:{user_id}:invites_per_week"
    await redis.delete(key)


# ---------------------------------------------------------------------------
# Idempotency key helpers
# ---------------------------------------------------------------------------


def make_dedup_key(
    from_profile_id: uuid.UUID,
    to_profile_id: uuid.UUID,
    synopsis: str,
) -> str:
    """Deterministic 60-second dedup key derived from sender+recipient+synopsis hash."""
    h = hashlib.sha256(
        f"{from_profile_id}:{to_profile_id}:{synopsis}".encode()
    ).hexdigest()[:16]
    return f"dedup:invite:{h}"


async def check_idempotency(
    redis: Redis,
    idem_key: str,
    ttl: int = 86400,
) -> bytes | None:
    """
    Return cached response bytes if key exists, else None.
    Caller sets the key after successful creation.
    """
    return await redis.get(f"idem:invite:{idem_key}")


async def set_idempotency(
    redis: Redis,
    idem_key: str,
    response_data: dict,
    ttl: int = 86400,
) -> None:
    await redis.setex(
        f"idem:invite:{idem_key}",
        ttl,
        json.dumps(response_data),
    )
