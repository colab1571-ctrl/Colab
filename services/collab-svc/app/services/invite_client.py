"""
invite-svc internal client — proxies request history endpoints.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from app.config import get_collab_settings

logger = logging.getLogger(__name__)
settings = get_collab_settings()


async def get_sent_requests(
    profile_id: uuid.UUID,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    return await _proxy_requests(
        profile_id=profile_id,
        direction="sent",
        status=status,
        cursor=cursor,
        limit=limit,
    )


async def get_received_requests(
    profile_id: uuid.UUID,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    return await _proxy_requests(
        profile_id=profile_id,
        direction="received",
        status=status,
        cursor=cursor,
        limit=limit,
    )


async def _proxy_requests(
    profile_id: uuid.UUID,
    direction: str,
    status: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    url = f"{settings.invite_svc_url}/internal/history/{direction}"
    headers = {"X-Service-Secret": settings.service_shared_secret}
    params: dict[str, Any] = {"profile_id": str(profile_id), "limit": limit}
    if status:
        params["status"] = status
    if cursor:
        params["cursor"] = cursor
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.error("invite-svc proxy failed (%s): %s", direction, exc)
        return {"data": [], "next_cursor": None, "total_count": 0}
