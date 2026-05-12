"""
Internal billing-svc client for credit reserve / commit / release and entitlement checks.

Uses pessimistic reservation pattern:
  1. reserve_credits() — deduct from wallet atomically; return reservation_id
  2. commit_reservation() — convert reserve → consume (on success)
  3. release_reservation() — refund credits (on failure / moderation block)
"""

from __future__ import annotations

import logging
import uuid

import httpx

from app.config import get_ai_settings

logger = logging.getLogger(__name__)


class InsufficientCreditsError(Exception):
    def __init__(self, balance: int, requested: int) -> None:
        self.balance = balance
        self.requested = requested
        super().__init__(f"Insufficient credits: have {balance}, need {requested}")


class EntitlementError(Exception):
    """User is not on a Premium or Pro tier."""


async def check_entitlement(user_id: uuid.UUID, http: httpx.AsyncClient) -> dict:
    """
    Returns entitlement dict from billing-svc cache.
    Raises EntitlementError if user is Free tier.
    """
    settings = get_ai_settings()
    resp = await http.get(
        f"{settings.billing_svc_url}/internal/entitlements/{user_id}",
        timeout=5.0,
    )
    if resp.status_code == 404:
        raise EntitlementError("No entitlement record found")
    resp.raise_for_status()
    data = resp.json()
    tier = data.get("tier", "free")
    if tier not in ("premium", "pro"):
        raise EntitlementError(f"User tier '{tier}' not eligible for AI commands")
    return data


async def reserve_credits(
    user_id: uuid.UUID,
    amount: int,
    reference_id: uuid.UUID,
    http: httpx.AsyncClient,
) -> uuid.UUID:
    """
    Pessimistically reserve `amount` credits for user.
    Returns reservation_id.
    Raises InsufficientCreditsError if balance insufficient.
    """
    settings = get_ai_settings()
    resp = await http.post(
        f"{settings.billing_svc_url}/internal/credits/reserve",
        json={
            "user_id": str(user_id),
            "amount": amount,
            "reference_kind": "ai_interaction",
            "reference_id": str(reference_id),
            "idempotency_key": f"ai-reserve:{reference_id}",
        },
        timeout=5.0,
    )
    if resp.status_code == 402:
        detail = resp.json()
        raise InsufficientCreditsError(
            balance=detail.get("balance", 0),
            requested=detail.get("requested", amount),
        )
    resp.raise_for_status()
    return uuid.UUID(resp.json()["reservation_id"])


async def commit_reservation(reservation_id: uuid.UUID, http: httpx.AsyncClient) -> None:
    """Convert reserve → consume on successful generation."""
    settings = get_ai_settings()
    resp = await http.post(
        f"{settings.billing_svc_url}/internal/credits/commit",
        json={"reservation_id": str(reservation_id)},
        timeout=5.0,
    )
    resp.raise_for_status()


async def release_reservation(
    reservation_id: uuid.UUID,
    reason: str,
    http: httpx.AsyncClient,
) -> None:
    """Release (refund) a credit reservation on failure."""
    settings = get_ai_settings()
    resp = await http.post(
        f"{settings.billing_svc_url}/internal/credits/release",
        json={"reservation_id": str(reservation_id), "reason": reason},
        timeout=5.0,
    )
    if resp.status_code >= 500:
        logger.error("Failed to release credit reservation %s: %s", reservation_id, resp.text)
    # Don't raise — best-effort refund; Celery retry will clean up
