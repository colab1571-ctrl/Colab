"""
billing-svc — Subscription state machine helpers.

Owns:
- upsert_subscription_from_stripe_event
- upsert_subscription_from_rc_event
- resolve_winning_subscription (cross-platform parity)
- apply_entitlements_for_user (writes EntitlementSnapshot rows)
- publish_entitlement_changed
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import aio_pika
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import EntitlementSnapshot, Subscription
from app.services.entitlements import (
    AXIS_REGISTRY,
    TIER_DEFAULTS,
    TIER_RANK,
    ACTIVE_STATUSES,
)

logger = logging.getLogger(__name__)

STRIPE_STATUS_MAP = {
    "trialing": "trialing",
    "active": "active",
    "past_due": "past_due",
    "canceled": "canceled",
    "unpaid": "past_due",
    "incomplete": "past_due",
    "incomplete_expired": "expired",
    "paused": "paused",
}

RC_STATUS_MAP = {
    "INITIAL_PURCHASE": "active",
    "RENEWAL": "active",
    "CANCELLATION": "canceled",
    "EXPIRATION": "expired",
    "BILLING_ISSUE": "past_due",
    "PRODUCT_CHANGE": "active",
    "SUBSCRIPTION_PAUSED": "paused",
}


async def upsert_subscription_from_stripe(
    db: AsyncSession,
    stripe_sub: dict[str, Any],
    user_id: uuid.UUID,
    tier: str,
    event_timestamp: datetime,
) -> Subscription:
    """Create or update a Subscription from a Stripe subscription object."""
    store_sub_id = stripe_sub.get("id", "")
    status_raw = stripe_sub.get("status", "active")
    status = STRIPE_STATUS_MAP.get(status_raw, "active")

    period_start = datetime.fromtimestamp(
        stripe_sub.get("current_period_start", 0), tz=UTC
    )
    period_end = datetime.fromtimestamp(
        stripe_sub.get("current_period_end", 0), tz=UTC
    )
    trial_end_ts = stripe_sub.get("trial_end")
    trial_end = datetime.fromtimestamp(trial_end_ts, tz=UTC) if trial_end_ts else None

    plan = (stripe_sub.get("items", {}).get("data") or [{}])[0]
    product_id = plan.get("price", {}).get("id", "unknown")
    interval = plan.get("price", {}).get("recurring", {}).get("interval", "month")
    billing_period = "year" if interval == "year" else "month"

    cancel_at_pe = stripe_sub.get("cancel_at_period_end", False)

    # Check existing
    result = await db.execute(
        select(Subscription).where(
            Subscription.store_subscription_id == store_sub_id,
            Subscription.source == "stripe",
        )
    )
    sub = result.scalar_one_or_none()

    if sub is None:
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=user_id,
            source="stripe",
            gateway="stripe",
            tier=tier,
            status=status,
            store_subscription_id=store_sub_id,
            store_product_id=product_id,
            billing_period=billing_period,
            current_period_start=period_start,
            current_period_end=period_end,
            cancel_at_period_end=cancel_at_pe,
            trial_end=trial_end,
            started_at=period_start,
        )
        db.add(sub)
    else:
        # Only apply if event is newer
        if event_timestamp <= sub.updated_at.replace(tzinfo=UTC) if sub.updated_at.tzinfo else event_timestamp:
            sub.tier = tier
            sub.status = status
            sub.current_period_start = period_start
            sub.current_period_end = period_end
            sub.cancel_at_period_end = cancel_at_pe
            sub.trial_end = trial_end
            if status in ("canceled", "expired") and not sub.canceled_at:
                sub.canceled_at = datetime.now(UTC)
            if status == "expired" and not sub.ended_at:
                sub.ended_at = datetime.now(UTC)

    await db.flush()
    return sub


async def upsert_subscription_from_rc(
    db: AsyncSession,
    rc_event: dict[str, Any],
    user_id: uuid.UUID,
    event_type: str,
    event_timestamp: datetime,
) -> Subscription:
    """Create or update a Subscription from a RevenueCat event."""
    sub_data = rc_event.get("subscriber", {})
    product_id = rc_event.get("product_id", "unknown")
    store = rc_event.get("store", "APP_STORE")
    gateway = "apple" if "APP_STORE" in store else "google"
    original_tx_id = rc_event.get("original_transaction_id", str(uuid.uuid4()))

    status = RC_STATUS_MAP.get(event_type, "active")
    period_end_ms = rc_event.get("expiration_at_ms")
    period_end = (
        datetime.fromtimestamp(period_end_ms / 1000, tz=UTC)
        if period_end_ms
        else datetime.now(UTC)
    )
    period_start_ms = rc_event.get("purchased_at_ms", 0)
    period_start = datetime.fromtimestamp(period_start_ms / 1000, tz=UTC) if period_start_ms else datetime.now(UTC)

    # Map product → tier (simplified; real mapping from EntitlementConfig lookup)
    tier = _map_product_to_tier(product_id)

    result = await db.execute(
        select(Subscription).where(
            Subscription.store_subscription_id == original_tx_id,
            Subscription.source == "revenuecat",
        )
    )
    sub = result.scalar_one_or_none()

    if sub is None:
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=user_id,
            source="revenuecat",
            gateway=gateway,
            tier=tier,
            status=status,
            store_subscription_id=original_tx_id,
            store_product_id=product_id,
            billing_period="month",  # RC doesn't always surface this; default
            current_period_start=period_start,
            current_period_end=period_end,
            started_at=period_start,
        )
        db.add(sub)
    else:
        sub.status = status
        sub.tier = tier
        sub.current_period_start = period_start
        sub.current_period_end = period_end
        if status in ("canceled", "expired") and not sub.canceled_at:
            sub.canceled_at = datetime.now(UTC)

    await db.flush()
    return sub


def _map_product_to_tier(product_id: str) -> str:
    """Map store product id to tier. Extend with real config lookup."""
    pid = product_id.lower()
    if "pro" in pid:
        return "pro"
    elif "premium" in pid:
        return "premium"
    return "free"


async def apply_entitlements_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    subscription: Subscription,
) -> None:
    """
    Write/update EntitlementSnapshot rows for all axes based on the winning subscription.
    Uses INSERT ... ON CONFLICT DO UPDATE (upsert).
    """
    tier = subscription.tier if subscription.status in ACTIVE_STATUSES else "free"
    tier_vals = TIER_DEFAULTS.get(tier, TIER_DEFAULTS["free"])

    for axis_key, value in tier_vals.items():
        # Upsert snapshot row
        stmt = (
            pg_insert(EntitlementSnapshot)
            .values(
                id=uuid.uuid4(),
                user_id=user_id,
                axis_key=axis_key,
                value={"v": value},
                source="subscription",
                source_ref=subscription.id,
                expires_at=subscription.current_period_end,
                updated_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                index_elements=["user_id", "axis_key", "source", "source_ref"],
                set_={
                    "value": {"v": value},
                    "expires_at": subscription.current_period_end,
                    "updated_at": datetime.now(UTC),
                },
            )
        )
        await db.execute(stmt)

    await db.flush()


async def publish_entitlement_changed(
    amqp_channel: aio_pika.Channel,
    user_id: uuid.UUID,
    axis_keys: list[str] | None = None,
    tier: str | None = None,
) -> None:
    """Publish entitlement.changed to RabbitMQ for cache invalidation."""
    import json
    payload: dict[str, Any] = {"user_id": str(user_id)}
    if axis_keys:
        payload["axis_keys"] = axis_keys
    if tier:
        payload["tier"] = tier

    message = aio_pika.Message(
        body=json.dumps(payload).encode(),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    await amqp_channel.default_exchange.publish(
        message, routing_key="entitlement.changed"
    )


async def publish_event(
    amqp_channel: aio_pika.Channel,
    routing_key: str,
    payload: dict[str, Any],
) -> None:
    import json
    message = aio_pika.Message(
        body=json.dumps(payload).encode(),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    await amqp_channel.default_exchange.publish(message, routing_key=routing_key)
