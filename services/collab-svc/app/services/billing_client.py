"""
billing-svc internal client for entitlement checks.
Uses HS256 service-to-service auth.
"""

from __future__ import annotations

import logging
import uuid

import httpx

from app.config import get_collab_settings

logger = logging.getLogger(__name__)
settings = get_collab_settings()


async def check_chat_export_entitlement(profile_id: uuid.UUID) -> bool:
    """
    Returns True if the user has chat_export = True via billing-svc internal API.
    Returns False on network errors (fail-closed for Premium gate).
    """
    url = f"{settings.billing_svc_url}/internal/entitlements/{profile_id}"
    headers = {"X-Service-Secret": settings.service_shared_secret}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                axes = data.get("axes", {})
                return bool(axes.get("chat_export", False))
            logger.warning(
                "billing-svc entitlement check returned %d for profile %s",
                resp.status_code,
                profile_id,
            )
            return False
    except Exception as exc:
        logger.error("billing-svc entitlement check failed: %s", exc)
        return False
