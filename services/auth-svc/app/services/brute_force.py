"""
auth-svc — Brute-force protection via Redis.

Login attempt counter: 10 failures per (email, IP) within 15 minutes → lock.
Exponential backoff after 5 failures.
Separate IP lock for pure IP-based hammering.
"""

from __future__ import annotations

import math
import time

import redis.asyncio as aioredis

from colab_common.errors import AuthError, RateLimitError
from colab_common.settings import get_settings

# Thresholds
MAX_ATTEMPTS = 10
WINDOW_SECONDS = 900  # 15 minutes
LOCKOUT_SECONDS = 900  # 15 minutes hard lock after threshold


def _get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    settings = get_settings()
    return aioredis.from_url(settings.redis.url, decode_responses=True)


async def record_failed_login(email: str, ip: str) -> None:
    """Increment failure counter. Raises AuthError if threshold reached."""
    r = _get_redis()
    key = f"login:attempts:{email}:{ip}"
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, WINDOW_SECONDS)
    results = await pipe.execute()
    count = int(results[0])

    if count >= MAX_ATTEMPTS:
        # Set a hard lock key so the account stays locked even after the counter expires
        lock_key = f"login:locked:{email}:{ip}"
        await r.setex(lock_key, LOCKOUT_SECONDS, "1")
        raise AuthError(
            f"Account locked due to too many failed attempts. "
            f"Try again in {LOCKOUT_SECONDS // 60} minutes."
        )

    if count >= 5:
        # Exponential backoff delay (advisory — not enforced server-side sleep)
        backoff = min(2 ** (count - 5), 60)
        raise RateLimitError(retry_after=backoff)


async def check_login_locked(email: str, ip: str) -> None:
    """Raise AuthError if the account-IP pair is currently hard-locked."""
    r = _get_redis()
    lock_key = f"login:locked:{email}:{ip}"
    if await r.exists(lock_key):
        ttl = await r.ttl(lock_key)
        raise AuthError(
            f"Account locked due to too many failed attempts. "
            f"Try again in {math.ceil(ttl / 60)} minutes."
        )


async def clear_failed_logins(email: str, ip: str) -> None:
    """Clear counters on successful login."""
    r = _get_redis()
    await r.delete(f"login:attempts:{email}:{ip}", f"login:locked:{email}:{ip}")


async def check_ip_rate_limit(ip: str, route: str, *, capacity: int = 20, window: int = 60) -> None:
    """Simple IP + route rate check (defense-in-depth; gateway also enforces)."""
    from colab_common.rate_limit import enforce_rate_limit

    key = f"rl:ip:{ip}:{route}"
    await enforce_rate_limit(key, capacity=capacity, refill_per_sec=capacity / window, retry_after=window)
