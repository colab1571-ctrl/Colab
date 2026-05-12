"""
colab_common.rate_limit — Redis token-bucket rate limiter.

Uses a Lua script for atomic refill + consume to avoid race conditions.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import redis.asyncio as aioredis
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from colab_common.errors import RateLimitError
from colab_common.settings import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lua script for atomic token-bucket refill + consume
# ---------------------------------------------------------------------------

_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_sec = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1]) or capacity
local last_refill = tonumber(bucket[2]) or now

local elapsed = now - last_refill
local refilled = math.floor(elapsed * refill_per_sec)
tokens = math.min(capacity, tokens + refilled)

if tokens >= 1 then
    tokens = tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, math.ceil(capacity / refill_per_sec) + 10)
    return {1, tokens}
else
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, math.ceil(capacity / refill_per_sec) + 10)
    return {0, tokens}
end
"""

# ---------------------------------------------------------------------------
# Core rate-limit check
# ---------------------------------------------------------------------------

_redis_client: aioredis.Redis | None = None  # type: ignore[type-arg]
_script_sha: str | None = None


def _get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(settings.redis.url, decode_responses=False)
    return _redis_client


async def _get_script_sha() -> str:
    global _script_sha
    if _script_sha is None:
        r = _get_redis()
        _script_sha = await r.script_load(_TOKEN_BUCKET_LUA)
    return _script_sha


async def check_rate_limit(
    key: str,
    *,
    capacity: int = 60,
    refill_per_sec: float = 1.0,
) -> tuple[bool, int]:
    """
    Attempt to consume one token from the bucket.

    Args:
        key: Unique bucket identifier (e.g., "rl:user:123:feed")
        capacity: Maximum burst capacity (tokens).
        refill_per_sec: How many tokens are added per second.

    Returns:
        (allowed, remaining_tokens)

    Raises:
        RateLimitError: if the bucket is empty.
    """
    r = _get_redis()
    sha = await _get_script_sha()
    now = int(time.time())
    result: list[int] = await r.evalsha(sha, 1, key, capacity, refill_per_sec, now)  # type: ignore[assignment]
    allowed = bool(result[0])
    remaining = int(result[1])
    return allowed, remaining


async def enforce_rate_limit(
    key: str,
    *,
    capacity: int = 60,
    refill_per_sec: float = 1.0,
    retry_after: int = 60,
) -> None:
    """
    Check and raise RateLimitError if limit exceeded.
    Convenience wrapper around check_rate_limit.
    """
    allowed, _ = await check_rate_limit(key, capacity=capacity, refill_per_sec=refill_per_sec)
    if not allowed:
        raise RateLimitError(retry_after=retry_after)


# ---------------------------------------------------------------------------
# Policy config
# ---------------------------------------------------------------------------


class RateLimitPolicy:
    def __init__(
        self,
        capacity: int,
        refill_per_sec: float,
        key_prefix: str = "rl",
    ) -> None:
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.key_prefix = key_prefix

    def key_for(self, identifier: str) -> str:
        return f"{self.key_prefix}:{identifier}"

    async def check(self, identifier: str) -> tuple[bool, int]:
        return await check_rate_limit(
            self.key_for(identifier),
            capacity=self.capacity,
            refill_per_sec=self.refill_per_sec,
        )

    async def enforce(self, identifier: str, retry_after: int = 60) -> None:
        await enforce_rate_limit(
            self.key_for(identifier),
            capacity=self.capacity,
            refill_per_sec=self.refill_per_sec,
            retry_after=retry_after,
        )


# ---------------------------------------------------------------------------
# Middleware (applied globally by gateway-svc)
# ---------------------------------------------------------------------------


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Global rate-limit middleware for the API gateway.
    Services may apply finer-grained limits via the dependency.
    """

    SKIP_PATHS = {"/healthz", "/ready", "/readyz", "/openapi.json", "/version"}

    def __init__(self, app: ASGIApp, *, global_capacity: int = 120) -> None:
        super().__init__(app)
        self.global_capacity = global_capacity

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        # Use user_id if authenticated, else IP
        user = getattr(request.state, "user", None)
        identifier = (
            f"user:{user.user_id}" if user else f"ip:{request.client.host if request.client else 'unknown'}"
        )
        key = f"rl:global:{identifier}"

        allowed, remaining = await check_rate_limit(
            key,
            capacity=self.global_capacity,
            refill_per_sec=self.global_capacity / 60.0,
        )

        if not allowed:
            raise RateLimitError(retry_after=60)

        response: Response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
