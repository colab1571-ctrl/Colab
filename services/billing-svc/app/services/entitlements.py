"""
billing-svc — Entitlement axis registry, resolver, and Redis cache.

AXIS_REGISTRY: frozen catalogue of all 13 axes with types + Free defaults.
Resolver: applies precedence (grant > subscription > promo > default).
Redis cache: `entitlements:{user_id}` TTL 1h, invalidated on entitlement.changed.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import EntitlementSnapshot, Subscription

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Axis registry — types and Free-tier defaults
# ---------------------------------------------------------------------------

AXIS_REGISTRY: dict[str, dict[str, Any]] = {
    "invites_per_week": {"type": "int", "default": 5},
    "ai_credits_per_month": {"type": "int", "default": 0},
    "ads_shown": {"type": "bool", "default": True},
    "chat_export": {"type": "bool", "default": False},
    "hide_from_non_premium": {"type": "bool", "default": False},
    "picked_for_you_priority": {
        "type": "enum",
        "choices": ["none", "standard", "high"],
        "default": "none",
    },
    "mockup_fidelity": {
        "type": "enum",
        "choices": ["off", "basic", "advanced"],
        "default": "off",
    },
    "portfolio_pdf_export": {"type": "bool", "default": False},
    "visibility_boost": {"type": "bool", "default": False},
    "support_priority": {
        "type": "enum",
        "choices": ["std", "fast", "fastest"],
        "default": "std",
    },
    "see_who_saved_you": {"type": "bool", "default": False},
    "feed_profiles_per_day": {"type": "int", "default": 30},
    "daily_save_cap": {"type": "int", "default": 50},
}

# Enum rank for precedence comparison
_ENUM_RANKS: dict[str, int] = {
    # picked_for_you_priority
    "none": 0, "standard": 1, "high": 2,
    # mockup_fidelity
    "off": 0, "basic": 1, "advanced": 2,
    # support_priority
    "std": 0, "fast": 1, "fastest": 2,
}

# Tier axis placeholder values (admin-configurable at runtime; these are seeds)
TIER_DEFAULTS: dict[str, dict[str, Any]] = {
    "free": {
        "invites_per_week": 5,
        "ai_credits_per_month": 0,
        "ads_shown": True,
        "chat_export": False,
        "hide_from_non_premium": False,
        "picked_for_you_priority": "none",
        "mockup_fidelity": "off",
        "portfolio_pdf_export": False,
        "visibility_boost": False,
        "support_priority": "std",
        "see_who_saved_you": False,
        "feed_profiles_per_day": 30,
        "daily_save_cap": 50,
    },
    "premium": {
        "invites_per_week": -1,
        "ai_credits_per_month": 200,
        "ads_shown": False,
        "chat_export": True,
        "hide_from_non_premium": True,
        "picked_for_you_priority": "standard",
        "mockup_fidelity": "basic",
        "portfolio_pdf_export": False,
        "visibility_boost": False,
        "support_priority": "fast",
        "see_who_saved_you": True,
        "feed_profiles_per_day": -1,
        "daily_save_cap": -1,
    },
    "pro": {
        "invites_per_week": -1,
        "ai_credits_per_month": 1000,
        "ads_shown": False,
        "chat_export": True,
        "hide_from_non_premium": True,
        "picked_for_you_priority": "high",
        "mockup_fidelity": "advanced",
        "portfolio_pdf_export": True,
        "visibility_boost": True,
        "support_priority": "fastest",
        "see_who_saved_you": True,
        "feed_profiles_per_day": -1,
        "daily_save_cap": -1,
    },
}

# Source precedence (higher index = higher priority)
SOURCE_PRIORITY = ["default", "promo", "subscription", "family_share", "grant"]

ACTIVE_STATUSES = {"trialing", "active", "past_due", "grace"}
TIER_RANK = {"free": 0, "premium": 1, "pro": 2}

REDIS_TTL = 3600  # 1 hour


@dataclass
class ResolvedEntitlements:
    axes: dict[str, Any]
    tier: str
    subscription_status: str | None
    current_period_end: datetime | None


# ---------------------------------------------------------------------------
# Value comparison helpers
# ---------------------------------------------------------------------------


def _higher_value(axis_key: str, a: Any, b: Any) -> Any:
    """Return the 'better' value for an axis (higher int, True over False, higher-rank enum)."""
    meta = AXIS_REGISTRY.get(axis_key, {})
    atype = meta.get("type", "bool")
    if atype == "int":
        # -1 == unlimited, which beats any positive
        if a == -1:
            return a
        if b == -1:
            return b
        return max(a, b)
    elif atype == "bool":
        return a or b
    elif atype == "enum":
        return a if _ENUM_RANKS.get(str(a), 0) >= _ENUM_RANKS.get(str(b), 0) else b
    return a


# ---------------------------------------------------------------------------
# Core resolver
# ---------------------------------------------------------------------------


async def resolve_entitlements(
    db: AsyncSession,
    user_id: uuid.UUID,
    now: datetime | None = None,
) -> ResolvedEntitlements:
    """
    Resolve entitlements for a user from EntitlementSnapshot table.
    Applies precedence: grant > subscription > promo > default.
    Within same source, higher value wins.
    """
    if now is None:
        now = datetime.now(UTC)

    # Find best subscription
    sub_q = await db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status.in_(list(ACTIVE_STATUSES)),
        )
        .order_by(Subscription.current_period_end.desc())
    )
    subs = sub_q.scalars().all()

    winning_tier = "free"
    winning_status: str | None = None
    winning_period_end: datetime | None = None

    if subs:
        # Highest-tier wins; tiebreak = latest period_end
        best = max(subs, key=lambda s: (TIER_RANK.get(s.tier, 0), s.current_period_end))
        winning_tier = best.tier
        winning_status = best.status
        winning_period_end = best.current_period_end

    # Load snapshots (non-expired)
    snap_q = await db.execute(
        select(EntitlementSnapshot).where(
            EntitlementSnapshot.user_id == user_id,
            (EntitlementSnapshot.expires_at.is_(None))
            | (EntitlementSnapshot.expires_at > now),
        )
    )
    snapshots = snap_q.scalars().all()

    # Build resolution map: axis_key → (best_value, best_source_priority)
    axis_resolution: dict[str, tuple[Any, int]] = {}

    for snap in snapshots:
        prio = SOURCE_PRIORITY.index(snap.source) if snap.source in SOURCE_PRIORITY else 0
        existing = axis_resolution.get(snap.axis_key)
        raw_value = snap.value if not isinstance(snap.value, dict) else snap.value.get("v", snap.value)
        if existing is None:
            axis_resolution[snap.axis_key] = (raw_value, prio)
        elif prio > existing[1]:
            axis_resolution[snap.axis_key] = (raw_value, prio)
        elif prio == existing[1]:
            better = _higher_value(snap.axis_key, raw_value, existing[0])
            axis_resolution[snap.axis_key] = (better, prio)

    # Fill missing axes from tier defaults
    tier_vals = TIER_DEFAULTS.get(winning_tier, TIER_DEFAULTS["free"])
    axes: dict[str, Any] = {}
    for axis_key in AXIS_REGISTRY:
        if axis_key in axis_resolution:
            axes[axis_key] = axis_resolution[axis_key][0]
        else:
            axes[axis_key] = tier_vals.get(axis_key, AXIS_REGISTRY[axis_key]["default"])

    return ResolvedEntitlements(
        axes=axes,
        tier=winning_tier,
        subscription_status=winning_status,
        current_period_end=winning_period_end,
    )


# ---------------------------------------------------------------------------
# Redis cache layer
# ---------------------------------------------------------------------------


def _cache_key(user_id: uuid.UUID | str) -> str:
    return f"entitlements:{user_id}"


async def get_cached_entitlements(
    redis: aioredis.Redis,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> ResolvedEntitlements:
    """Return cached entitlements or resolve + cache."""
    key = _cache_key(user_id)
    raw = await redis.get(key)
    if raw:
        try:
            data = json.loads(raw)
            # Reconstruct
            period_end = (
                datetime.fromisoformat(data["current_period_end"])
                if data.get("current_period_end")
                else None
            )
            return ResolvedEntitlements(
                axes=data["axes"],
                tier=data["tier"],
                subscription_status=data.get("subscription_status"),
                current_period_end=period_end,
            )
        except Exception:
            logger.warning("Cache parse error for %s; re-resolving", key)

    resolved = await resolve_entitlements(db, user_id)
    await _set_cache(redis, user_id, resolved)
    return resolved


async def _set_cache(
    redis: aioredis.Redis,
    user_id: uuid.UUID,
    resolved: ResolvedEntitlements,
) -> None:
    key = _cache_key(user_id)
    data = {
        "axes": resolved.axes,
        "tier": resolved.tier,
        "subscription_status": resolved.subscription_status,
        "current_period_end": (
            resolved.current_period_end.isoformat() if resolved.current_period_end else None
        ),
    }
    await redis.set(key, json.dumps(data), ex=REDIS_TTL)


async def invalidate_entitlement_cache(redis: aioredis.Redis, user_id: uuid.UUID | str) -> None:
    """Called when entitlement.changed event received."""
    await redis.delete(_cache_key(user_id))
