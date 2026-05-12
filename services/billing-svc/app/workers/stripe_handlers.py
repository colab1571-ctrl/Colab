"""
billing-svc — Stripe webhook event handlers.

Each handler is idempotent: idempotency_key derived deterministically from event id.
Out-of-order guard: compare event.created to subscription.updated_at; skip if stale.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Customer, Invoice, Subscription
from app.services.credits import credit_purchase, grant_subscription_credits
from app.services.dunning import mark_recovered, open_dunning_case
from app.services.subscriptions import (
    apply_entitlements_for_user,
    publish_entitlement_changed,
    publish_event,
    upsert_subscription_from_stripe,
)

logger = logging.getLogger(__name__)


def _stripe_tier_from_product(product_id: str) -> str:
    pid = product_id.lower()
    if "pro" in pid:
        return "pro"
    elif "premium" in pid:
        return "premium"
    return "free"


async def _get_user_id_from_stripe_customer(
    db: AsyncSession,
    stripe_customer_id: str,
) -> uuid.UUID | None:
    result = await db.execute(
        select(Customer).where(Customer.stripe_customer_id == stripe_customer_id)
    )
    customer = result.scalar_one_or_none()
    return customer.user_id if customer else None


async def handle_checkout_completed(
    db: AsyncSession,
    event: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """checkout.session.completed — create/link customer, fire subscription flow."""
    session = event.get("data", {}).get("object", {})
    mode = session.get("mode")
    client_ref = session.get("client_reference_id")
    stripe_customer_id = session.get("customer")

    if not client_ref:
        logger.warning("checkout.session.completed missing client_reference_id")
        return

    try:
        user_id = uuid.UUID(client_ref)
    except ValueError:
        logger.error("Invalid user_id in client_reference_id: %s", client_ref)
        return

    # Ensure Customer row exists
    result = await db.execute(
        select(Customer).where(Customer.user_id == user_id)
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        customer = Customer(
            id=uuid.uuid4(),
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            revenuecat_user_id=str(user_id),
        )
        db.add(customer)
    elif not customer.stripe_customer_id and stripe_customer_id:
        customer.stripe_customer_id = stripe_customer_id

    await db.flush()

    if mode == "payment":
        # Credit bundle purchase
        amount_subtotal = session.get("amount_subtotal", 0)
        session_id = session.get("id", "")
        idem_key = f"purchase:{session_id}"
        # Credits mapping from line items (simplified: metadata or config lookup)
        credit_amount = session.get("metadata", {}).get("credit_amount", 0)
        if credit_amount:
            await credit_purchase(
                db=db,
                user_id=user_id,
                amount=int(credit_amount),
                reference_kind="stripe_checkout",
                reference_id=session_id,
                idempotency_key=idem_key,
            )
            await publish_event(
                amqp_channel,
                "credits.purchased",
                {"user_id": str(user_id), "amount": credit_amount, "source": "stripe", "reference": session_id},
            )
            await db.commit()

    logger.info("checkout.session.completed processed for user %s", user_id)


async def handle_sub_created(
    db: AsyncSession,
    event: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """customer.subscription.created"""
    sub_obj = event.get("data", {}).get("object", {})
    stripe_customer_id = sub_obj.get("customer", "")
    event_ts = datetime.fromtimestamp(event.get("created", 0), tz=UTC)

    user_id = await _get_user_id_from_stripe_customer(db, stripe_customer_id)
    if user_id is None:
        logger.warning("No Customer found for stripe_customer_id=%s", stripe_customer_id)
        return

    items = sub_obj.get("items", {}).get("data", [{}])
    product_id = items[0].get("price", {}).get("product", "") if items else ""
    tier = _stripe_tier_from_product(product_id)

    sub = await upsert_subscription_from_stripe(db, sub_obj, user_id, tier, event_ts)
    await apply_entitlements_for_user(db, user_id, sub)
    await publish_entitlement_changed(amqp_channel, user_id, tier=tier)
    await publish_event(
        amqp_channel, "subscription.activated",
        {"user_id": str(user_id), "tier": tier, "source": "stripe"},
    )
    await db.commit()


async def handle_sub_updated(
    db: AsyncSession,
    event: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """customer.subscription.updated"""
    sub_obj = event.get("data", {}).get("object", {})
    stripe_customer_id = sub_obj.get("customer", "")
    event_ts = datetime.fromtimestamp(event.get("created", 0), tz=UTC)

    user_id = await _get_user_id_from_stripe_customer(db, stripe_customer_id)
    if user_id is None:
        return

    items = sub_obj.get("items", {}).get("data", [{}])
    product_id = items[0].get("price", {}).get("product", "") if items else ""
    tier = _stripe_tier_from_product(product_id)

    sub = await upsert_subscription_from_stripe(db, sub_obj, user_id, tier, event_ts)
    await apply_entitlements_for_user(db, user_id, sub)
    await publish_entitlement_changed(amqp_channel, user_id, tier=tier)
    await db.commit()


async def handle_sub_canceled(
    db: AsyncSession,
    event: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """customer.subscription.deleted"""
    sub_obj = event.get("data", {}).get("object", {})
    stripe_customer_id = sub_obj.get("customer", "")
    event_ts = datetime.fromtimestamp(event.get("created", 0), tz=UTC)

    user_id = await _get_user_id_from_stripe_customer(db, stripe_customer_id)
    if user_id is None:
        return

    sub = await upsert_subscription_from_stripe(db, sub_obj, user_id, "free", event_ts)
    # Entitlements drop to Free
    await apply_entitlements_for_user(db, user_id, sub)
    await publish_entitlement_changed(amqp_channel, user_id, tier="free")
    await publish_event(
        amqp_channel, "subscription.canceled",
        {"user_id": str(user_id), "tier": sub.tier},
    )
    await db.commit()


async def handle_invoice_paid(
    db: AsyncSession,
    event: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """invoice.paid — mirror invoice, grant subscription credits."""
    inv_obj = event.get("data", {}).get("object", {})
    stripe_customer_id = inv_obj.get("customer", "")
    invoice_id = inv_obj.get("id", "")
    amount_paid = inv_obj.get("amount_paid", 0)
    currency = inv_obj.get("currency", "usd").upper()
    tax = inv_obj.get("tax", 0) or 0
    period_start_ts = inv_obj.get("period_start")
    period_end_ts = inv_obj.get("period_end")
    hosted_url = inv_obj.get("hosted_invoice_url")
    pdf = inv_obj.get("invoice_pdf")

    user_id = await _get_user_id_from_stripe_customer(db, stripe_customer_id)
    if user_id is None:
        return

    # Upsert Invoice
    result = await db.execute(
        select(Invoice).where(Invoice.stripe_invoice_id == invoice_id)
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        inv = Invoice(
            id=uuid.uuid4(),
            user_id=user_id,
            stripe_invoice_id=invoice_id,
            amount_minor=amount_paid,
            currency=currency,
            tax_minor=tax,
            status="paid",
            period_start=datetime.fromtimestamp(period_start_ts, tz=UTC) if period_start_ts else None,
            period_end=datetime.fromtimestamp(period_end_ts, tz=UTC) if period_end_ts else None,
            hosted_invoice_url=hosted_url,
            pdf_url=pdf,
        )
        db.add(inv)
    else:
        inv.status = "paid"

    # Grant subscription credits on renewal
    sub_id_str = inv_obj.get("subscription")
    if sub_id_str:
        sub_result = await db.execute(
            select(Subscription).where(Subscription.store_subscription_id == sub_id_str)
        )
        sub = sub_result.scalar_one_or_none()
        if sub and sub.tier != "free":
            from app.services.entitlements import TIER_DEFAULTS
            credits = TIER_DEFAULTS.get(sub.tier, {}).get("ai_credits_per_month", 0)
            if credits > 0:
                await grant_subscription_credits(
                    db, user_id, credits, sub.id,
                    sub.current_period_start,
                )
                await publish_event(
                    amqp_channel, "credits.granted",
                    {"user_id": str(user_id), "amount": credits, "reason": "subscription_renewal"},
                )

    # Recover dunning if open
    if sub_id_str:
        sub_result2 = await db.execute(
            select(Subscription).where(Subscription.store_subscription_id == sub_id_str)
        )
        sub2 = sub_result2.scalar_one_or_none()
        if sub2:
            await mark_recovered(db, sub2.id)

    await db.commit()


async def handle_invoice_failed(
    db: AsyncSession,
    event: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """invoice.payment_failed — open dunning case, set past_due."""
    inv_obj = event.get("data", {}).get("object", {})
    stripe_customer_id = inv_obj.get("customer", "")
    sub_id_str = inv_obj.get("subscription")

    user_id = await _get_user_id_from_stripe_customer(db, stripe_customer_id)
    if user_id is None:
        return

    if sub_id_str:
        sub_result = await db.execute(
            select(Subscription).where(Subscription.store_subscription_id == sub_id_str)
        )
        sub = sub_result.scalar_one_or_none()
        if sub:
            sub.status = "past_due"
            await db.flush()
            await open_dunning_case(db, user_id, sub.id)
            await publish_event(
                amqp_channel, "subscription.past_due",
                {"user_id": str(user_id), "tier": sub.tier},
            )

    await db.commit()


async def handle_charge_refunded(
    db: AsyncSession,
    event: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """charge.refunded — finalize refund request, update subscription."""
    charge_obj = event.get("data", {}).get("object", {})
    stripe_customer_id = charge_obj.get("customer", "")
    refund_id = (charge_obj.get("refunds", {}).get("data") or [{}])[0].get("id", "")

    user_id = await _get_user_id_from_stripe_customer(db, stripe_customer_id)
    if user_id is None:
        return

    # Update RefundRequest if exists
    from app.models.billing import RefundRequest
    result = await db.execute(
        select(RefundRequest).where(
            RefundRequest.stripe_refund_id == refund_id,
            RefundRequest.user_id == user_id,
        )
    )
    rr = result.scalar_one_or_none()
    if rr and rr.status in ("pending", "auto_approved"):
        rr.status = "approved"
        rr.decided_at = datetime.now(UTC)

    # Update Invoice
    inv_id = charge_obj.get("invoice")
    if inv_id:
        inv_result = await db.execute(
            select(Invoice).where(Invoice.stripe_invoice_id == inv_id)
        )
        inv = inv_result.scalar_one_or_none()
        if inv:
            inv.status = "refunded"

    await publish_event(
        amqp_channel, "refund.granted",
        {"user_id": str(user_id), "amount": charge_obj.get("amount_refunded", 0)},
    )
    await publish_entitlement_changed(amqp_channel, user_id)
    await db.commit()
