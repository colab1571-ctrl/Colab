"""Health, readiness, version, and feature-flag endpoints."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import GIT_SHA, IMAGE_TAG, SERVICE_NAME, UPSTREAM_URLS, settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/healthz", include_in_schema=False)
async def liveness() -> dict[str, str]:
    """Liveness probe — returns 200 if process is up."""
    return {"status": "ok"}


@router.get("/ready", include_in_schema=True)
async def readiness() -> JSONResponse:
    """
    Readiness probe — pings Redis + at least hello-svc.
    Returns 200 if all checks pass; 503 if any fail.
    """
    checks: dict[str, str] = {}
    all_ok = True

    # Redis check
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis.url, decode_responses=True)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.warning("Redis not reachable: %s", exc)
        checks["redis"] = "error"
        all_ok = False

    # hello-svc check (P1 only; in production probe all configured upstreams)
    hello_url = UPSTREAM_URLS.get("hello", "")
    if hello_url:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{hello_url}/healthz")
                checks["hello-svc"] = "ok" if resp.status_code == 200 else f"http-{resp.status_code}"
                if resp.status_code != 200:
                    all_ok = False
        except Exception as exc:
            logger.warning("hello-svc not reachable: %s", exc)
            checks["hello-svc"] = "error"
            # Not fatal for readiness in P1 (upstream may not be deployed)

    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ok" if all_ok else "degraded", "checks": checks},
    )


@router.get("/version", include_in_schema=True)
async def version() -> dict[str, str]:
    """Image tag + git SHA. Used by CI to verify deployments."""
    return {
        "service": SERVICE_NAME,
        "git_sha": GIT_SHA,
        "image_tag": IMAGE_TAG,
    }


@router.get("/v1/flags", include_in_schema=True)
async def feature_flags() -> dict[str, object]:
    """
    Expose server-side feature flags to clients.
    PostHog is primary; this is the fallback/override layer.
    """
    f = settings.features
    return {
        "ai_mockups_enabled": f.ai_mockups_enabled,
        "in_chat_ai_enabled": f.in_chat_ai_enabled,
        "ads_enabled": f.ads_enabled,
        "marketing_notifications": f.marketing_notifications,
        "region_allowlist": f.allowed_regions,
    }
