"""
support-svc — Status page endpoint.

GET /v1/support/status

Proxies Statuspage.io public summary JSON; caches in Redis for 60 seconds.
Falls back to a stub "operational" response if Statuspage.io is unreachable.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter

from app.config import get_support_settings
from app.schemas import StatusComponentOut, StatusOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/support", tags=["status"])

_redis_client: aioredis.Redis | None = None

CACHE_KEY = "support:status_page"

_STUB_RESPONSE = StatusOut(
    status="operational",
    description="All systems operational",
    incidents=[],
    components=[
        StatusComponentOut(name="API", status="operational"),
        StatusComponentOut(name="Chat", status="operational"),
        StatusComponentOut(name="Matching", status="operational"),
        StatusComponentOut(name="Media", status="operational"),
    ],
    fetched_at=datetime.now(tz=timezone.utc),
)


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        cfg = get_support_settings()
        _redis_client = aioredis.from_url(cfg.redis_url, decode_responses=True)
    return _redis_client


def _parse_statuspage_response(data: dict) -> StatusOut:
    """Normalize Statuspage.io summary JSON into StatusOut."""
    status_info = data.get("status", {})
    indicator = status_info.get("indicator", "operational")
    description = status_info.get("description", "All systems operational")

    # Statuspage.io uses indicator: none | minor | major | critical
    status_str = "operational" if indicator == "none" else indicator

    incidents = data.get("incidents", [])
    normalized_incidents = [
        {"id": inc.get("id"), "name": inc.get("name"), "status": inc.get("status")}
        for inc in incidents
    ]

    components = [
        StatusComponentOut(
            name=c.get("name", ""),
            status=c.get("status", "operational"),
        )
        for c in data.get("components", [])
    ]

    return StatusOut(
        status=status_str,
        description=description,
        incidents=normalized_incidents,
        components=components,
        fetched_at=datetime.now(tz=timezone.utc),
    )


@router.get("/status", response_model=StatusOut)
async def get_status() -> StatusOut:
    """
    Fetch live outage status (public endpoint, no auth required).
    Cached in Redis for 60 seconds.
    """
    cfg = get_support_settings()
    r = _get_redis()

    # Check cache
    cached = await r.get(CACHE_KEY)
    if cached:
        try:
            data = json.loads(cached)
            return StatusOut(**data)
        except Exception:
            pass

    # Fetch from Statuspage.io
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(cfg.statuspage_summary_url)
            resp.raise_for_status()
            result = _parse_statuspage_response(resp.json())
    except Exception as exc:
        logger.warning("Statuspage.io fetch failed: %s — returning stub", exc)
        result = _STUB_RESPONSE.model_copy(
            update={"fetched_at": datetime.now(tz=timezone.utc)}
        )

    # Cache result
    try:
        await r.set(
            CACHE_KEY,
            result.model_dump_json(),
            ex=cfg.status_page_cache_ttl,
        )
    except Exception as exc:
        logger.warning("Redis cache write failed: %s", exc)

    return result
