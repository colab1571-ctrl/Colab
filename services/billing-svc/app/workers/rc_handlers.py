"""
billing-svc — RevenueCat webhook event handlers.

Event shapes: RC webhook body has { event: { type, app_user_id, ... } }
or at top-level depending on version. We normalise both.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Customer
from app.services.credits import credit_purchase, grant_subscription_credits
from app.services.dunning import mark_recovered, open_dunning_case
from app.services.subscriptions import (
    apply_entitlements_for_user,
    publish_entitlement_changed,
    publish_event,
    upsert_subscription_from_rc,
)

logger = logging.getLogger(__name__)


def _extract_rc_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise RC event shape: may be { event: {...} } or flat."""
    if "event" in payload:
        return payload["event"]
    return payload


def _parse_user_id(rc_event: dict[str, Any]) -> uuid.UUID | None:
    app_user_id = rc_event.get("app_user_id", "")
    try:
        return uuid.UUID(app_user_id)
    except ValueError:
        logger.error("Invalid app_user_id from RC: %s", app_user_id)
        return None


async def _ensure_customer(db: AsyncSession, user_id: uuid.UUID) -> Customer:
    result = await db.execute(select(Customer).where(Customer.user_id == user_id))
    customer = result.scalar_one_or_none()
    if customer is None:
        customer = Customer(
            id=uuid.uuid4(),
            user_id=user_id,
            revenuecat_user_id=str(user_id),
        )
        db.add(customer)
        await db.flush()
    return customer


async def handle_rc_initial_purchase(
    db: AsyncSession,
    payload: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """INITIAL_PURCHASE — new mobile subscription."""
    rc_event = _extract_rc_event(payload)
    user_id = _parse_user_id(rc_event)
    if user_id is None:
        return

    await _ensure_customer(db, user_id)
    event_ts = datetime.fromtimestamp(
        (rc_event.get("purchased_at_ms", 0) or 0) / 1000, tz=UTC
    )

    sub = await upsert_subscription_from_rc(db, rc_event, user_id, "INITIAL_PURCHASE", event_ts)
    await apply_entitlements_for_user(db, user_id, sub)

    # Grant credits for first period
    from app.services.entitlements import TIER_DEFAULTS
    credits = TIER_DEFAULTS.get(sub.tier, {}).get("ai_credits_per_month", 0)
    if credits > 0:
        await grant_subscription_credits(db, user_id, credits, sub.id, sub.current_period_start)
        await publish_event(
            amqp_channel, "credits.granted",
            {"user_id": str(user_id), "amount": credits, "reason": "initial_purchase"},
        )

    await publish_entitlement_changed(amqp_channel, user_id, tier=sub.tier)
    await publish_event(
        amqp_channel, "subscription.activated",
        {"user_id": str(user_id), "tier": sub.tier, "source": "revenuecat"},
    )
    await db.commit()
    logger.info("RC INITIAL_PURCHASE processed for user %s tier=%s", user_id, sub.tier)


async def handle_rc_renewal(
    db: AsyncSession,
    payload: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """RENEWAL — subscription renewed successfully."""
    rc_event = _extract_rc_event(payload)
    user_id = _parse_user_id(rc_event)
    if user_id is None:
        return

    event_ts = datetime.fromtimestamp(
        (rc_event.get("purchased_at_ms", 0) or 0) / 1000, tz=UTC
    )

    sub = await upsert_subscription_from_rc(db, rc_event, user_id, "RENEWAL", event_ts)
    await apply_entitlements_for_user(db, user_id, sub)
    await mark_recovered(db, sub.id)

    from app.services.entitlements import TIER_DEFAULTS
    credits = TIER_DEFAULTS.get(sub.tier, {}).get("ai_credits_per_month", 0)
    if credits > 0:
        await grant_subscription_credits(db, user_id, credits, sub.id, sub.current_period_start)
        await publish_event(
            amqp_channel, "credits.granted",
            {"user_id": str(user_id), "amount": credits, "reason": "renewal"},
        )

    await publish_entitlement_changed(amqp_channel, user_id, tier=sub.tier)
    await db.commit()


async def handle_rc_cancellation(
    db: AsyncSession,
    payload: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """CANCELLATION — user or Apple/Google canceled."""
    rc_event = _extract_rc_event(payload)
    user_id = _parse_user_id(rc_event)
    if user_id is None:
        return

    event_ts = datetime.fromtimestamp(
        (rc_event.get("cancel_reason_ms", rc_event.get("purchased_at_ms", 0)) or 0) / 1000,
        tz=UTC,
    )

    sub = await upsert_subscription_from_rc(db, rc_event, user_id, "CANCELLATION", event_ts)
    await apply_entitlements_for_user(db, user_id, sub)
    await publish_entitlement_changed(amqp_channel, user_id, tier="free")
    await publish_event(
        amqp_channel, "subscription.canceled",
        {"user_id": str(user_id), "tier": sub.tier},
    )
    await db.commit()


async def handle_rc_expiration(
    db: AsyncSession,
    payload: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """EXPIRATION — subscription period ended without renewal."""
    rc_event = _extract_rc_event(payload)
    user_id = _parse_user_id(rc_event)
    if user_id is None:
        return

    event_ts = datetime.fromtimestamp(
        (rc_event.get("expiration_at_ms", 0) or 0) / 1000, tz=UTC
    )

    sub = await upsert_subscription_from_rc(db, rc_event, user_id, "EXPIRATION", event_ts)
    await apply_entitlements_for_user(db, user_id, sub)
    await publish_entitlement_changed(amqp_channel, user_id, tier="free")
    await db.commit()


async def handle_rc_billing_issue(
    db: AsyncSession,
    payload: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """BILLING_ISSUE — mobile payment failed; open dunning case."""
    rc_event = _extract_rc_event(payload)
    user_id = _parse_user_id(rc_event)
    if user_id is None:
        return

    event_ts = datetime.fromtimestamp(
        (rc_event.get("purchased_at_ms", 0) or 0) / 1000, tz=UTC
    )

    sub = await upsert_subscription_from_rc(db, rc_event, user_id, "BILLING_ISSUE", event_ts)
    await open_dunning_case(db, user_id, sub.id)
    await publish_event(
        amqp_channel, "subscription.past_due",
        {"user_id": str(user_id), "tier": sub.tier},
    )
    await db.commit()


async def handle_rc_one_off(
    db: AsyncSession,
    payload: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """NON_RENEWING_PURCHASE — credit bundle one-off purchase on mobile."""
    rc_event = _extract_rc_event(payload)
    user_id = _parse_user_id(rc_event)
    if user_id is None:
        return

    rc_event_id = rc_event.get("id", str(uuid.uuid4()))
    idem_key = f"purchase:{rc_event_id}"

    # Credit amount from product metadata (simplified: parse from product_id)
    product_id = rc_event.get("product_id", "")
    credit_amount = _parse_credit_amount(product_id)

    if credit_amount > 0:
        await credit_purchase(
            db=db,
            user_id=user_id,
            amount=credit_amount,
            reference_kind="rc_event",
            reference_id=rc_event_id,
            idempotency_key=idem_key,
        )
        await publish_event(
            amqp_channel, "credits.purchased",
            {"user_id": str(user_id), "amount": credit_amount, "source": "revenuecat", "reference": rc_event_id},
        )

    await db.commit()


def _parse_credit_amount(product_id: str) -> int:
    """Derive credit amount from product_id. Extend with config lookup."""
    # Example: colab_credits_100, colab_credits_500
    parts = product_id.lower().split("_")
    for part in reversed(parts):
        try:
            return int(part)
        except ValueError:
            continue
    return 0


async def handle_rc_product_change(
    db: AsyncSession,
    payload: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """PRODUCT_CHANGE — upgrade or downgrade."""
    rc_event = _extract_rc_event(payload)
    user_id = _parse_user_id(rc_event)
    if user_id is None:
        return

    event_ts = datetime.fromtimestamp(
        (rc_event.get("purchased_at_ms", 0) or 0) / 1000, tz=UTC
    )

    sub = await upsert_subscription_from_rc(db, rc_event, user_id, "PRODUCT_CHANGE", event_ts)
    await apply_entitlements_for_user(db, user_id, sub)
    await publish_entitlement_changed(amqp_channel, user_id, tier=sub.tier)
    await db.commit()


async def handle_rc_alias_merge(
    db: AsyncSession,
    payload: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """SUBSCRIBER_ALIAS — RC merged two user records (pre-login purchase recovery)."""
    rc_event = _extract_rc_event(payload)
    # Log for audit; may require manual reconciliation
    logger.warning(
        "RC SUBSCRIBER_ALIAS event received: %s — manual reconciliation may be needed",
        rc_event.get("app_user_id"),
    )
    await db.commit()
