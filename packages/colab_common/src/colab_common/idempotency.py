"""
colab_common.idempotency — Idempotency-Key middleware backed by Redis.

Caches response body keyed by (user_id, method, path, idempotency_key).
TTL: 24 hours. Replays cached response on duplicate key within TTL.
Skips GET, HEAD, OPTIONS.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import redis.asyncio as aioredis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from colab_common.settings import get_settings

logger = logging.getLogger(__name__)

_IDEMPOTENCY_TTL = 86400  # 24 hours
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

_redis_client: aioredis.Redis | None = None  # type: ignore[type-arg]


def _get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(settings.redis.url, decode_responses=True)
    return _redis_client


def _make_cache_key(user_id: str, method: str, path: str, idempotency_key: str) -> str:
    raw = f"{user_id}:{method}:{path}:{idempotency_key}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"idempotency:{digest}"


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    If the request carries an 'Idempotency-Key' header and the method is mutating,
    check if we've seen this key before:
      - If yes: return cached response (no re-execution).
      - If no: execute, cache result, return.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return await call_next(request)

        user = getattr(request.state, "user", None)
        user_id = user.user_id if user else "anonymous"

        cache_key = _make_cache_key(user_id, request.method, request.url.path, idempotency_key)
        redis = _get_redis()

        cached = await redis.get(cache_key)
        if cached:
            logger.debug("Idempotency cache hit", extra={"key": idempotency_key})
            data = json.loads(cached)
            return JSONResponse(
                status_code=data["status_code"],
                content=data["body"],
                headers={"X-Idempotency-Replayed": "true"},
            )

        # Execute the request
        response: Response = await call_next(request)

        # Only cache successful responses (2xx)
        if 200 <= response.status_code < 300:
            # Read response body (consume the stream)
            body_bytes = b""
            async for chunk in response.body_iterator:  # type: ignore[attr-defined]
                if isinstance(chunk, bytes):
                    body_bytes += chunk
                else:
                    body_bytes += chunk.encode()

            try:
                body_json = json.loads(body_bytes)
            except (json.JSONDecodeError, ValueError):
                body_json = {"raw": body_bytes.decode(errors="replace")}

            payload = json.dumps({"status_code": response.status_code, "body": body_json})
            await redis.setex(cache_key, _IDEMPOTENCY_TTL, payload)

            return JSONResponse(
                status_code=response.status_code,
                content=body_json,
                headers=dict(response.headers),
            )

        return response
