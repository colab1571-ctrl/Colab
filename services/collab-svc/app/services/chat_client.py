"""
chat-svc internal client for injecting system messages from collab-svc.

Called by Celery consumers after task status changes.
Uses HS256 service-to-service auth (per RECONCILIATION.md resolution §2).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from app.config import get_collab_settings

logger = logging.getLogger(__name__)
settings = get_collab_settings()


async def post_system_message(
    chat_room_id: uuid.UUID,
    body: str,
    metadata: dict[str, Any],
) -> bool:
    """
    POST /chat/rooms/{chat_room_id}/system-message to chat-svc internal endpoint.
    Returns True on success, False on error (best-effort; system messages are non-critical).
    """
    url = f"{settings.chat_svc_url}/internal/rooms/{chat_room_id}/system-message"
    headers = {"X-Service-Secret": settings.service_shared_secret}
    payload = {"body": body, "metadata": metadata}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                logger.debug("System message posted to room %s", chat_room_id)
                return True
            logger.warning(
                "chat-svc system-message returned %d for room %s",
                resp.status_code,
                chat_room_id,
            )
            return False
    except Exception as exc:
        logger.error("Failed to post system message to chat-svc: %s", exc)
        return False


async def check_whiteboard_export_entitlement(profile_id: uuid.UUID) -> bool:
    """
    Check whether the profile has the whiteboard_hi_res_export entitlement.
    Delegates to billing-svc (same pattern as check_chat_export_entitlement).
    """
    url = f"{settings.billing_svc_url}/internal/entitlements/{profile_id}"
    headers = {"X-Service-Secret": settings.service_shared_secret}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                axes = resp.json().get("axes", {})
                return bool(axes.get("whiteboard_hi_res_export", False))
            return False
    except Exception as exc:
        logger.error("billing-svc entitlement check failed: %s", exc)
        return False
