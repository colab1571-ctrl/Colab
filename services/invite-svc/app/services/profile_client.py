"""
invite-svc — Lightweight profile-svc HTTP client.

Fetches minimal profile card data for inbox/sent list responses.
Uses internal service-to-service auth (X-Internal-Service header).
"""

from __future__ import annotations

import logging
import uuid

import httpx

from app.config import get_settings
from app.schemas.invite import ProfileCard

logger = logging.getLogger(__name__)

_FALLBACK_CARD = ProfileCard(
    profile_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
    display_name=None,
    avatar_url=None,
    city=None,
    top_vocation=None,
)


async def fetch_profile_card(profile_id: uuid.UUID) -> ProfileCard:
    """
    Fetch a minimal profile card from profile-svc /internal/profiles/{id}/card.
    Returns a stub on any error to avoid cascading failures.
    """
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=0.5) as client:
            resp = await client.get(
                f"{settings.profile_svc_url}/internal/profiles/{profile_id}/card",
                headers={"X-Internal-Service": "invite-svc"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return ProfileCard(
                    profile_id=profile_id,
                    display_name=data.get("display_name"),
                    avatar_url=data.get("avatar_url"),
                    city=data.get("location_city"),
                    top_vocation=data.get("top_vocation"),
                )
    except Exception as exc:
        logger.warning("profile-svc card fetch failed for %s: %s", profile_id, exc)

    card = ProfileCard(
        profile_id=profile_id,
        display_name=None,
        avatar_url=None,
        city=None,
        top_vocation=None,
    )
    return card


async def fetch_profile_cards(
    profile_ids: list[uuid.UUID],
) -> dict[uuid.UUID, ProfileCard]:
    """Batch fetch multiple profile cards. Returns dict keyed by profile_id."""
    import asyncio

    results = await asyncio.gather(
        *[fetch_profile_card(pid) for pid in profile_ids],
        return_exceptions=True,
    )
    out: dict[uuid.UUID, ProfileCard] = {}
    for pid, result in zip(profile_ids, results):
        if isinstance(result, ProfileCard):
            out[pid] = result
        else:
            out[pid] = ProfileCard(
                profile_id=pid,
                display_name=None,
                avatar_url=None,
                city=None,
                top_vocation=None,
            )
    return out
