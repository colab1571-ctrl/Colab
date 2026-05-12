"""
billing-svc — Webhook ingestion pipeline.

Common pipeline:
  1. Verify signature (provider-specific)
  2. INSERT into WebhookEventLedger (unique on provider+event_id) → dedupes replays
  3. Enqueue Celery task process_webhook_event(ledger_id)
  4. Return 200 within <5s

Idempotency:
  - Provider event id → unique constraint on WebhookEventLedger
  - Downstream writes use deterministic idempotency_key derived from event
  - Out-of-order: compare event_timestamp to subscription.updated_at; skip stale
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import stripe
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import WebhookEventLedger
from colab_common.errors import AuthError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


def verify_stripe_signature(
    raw_body: bytes,
    sig_header: str,
    webhook_secret: str,
) -> dict[str, Any]:
    """
    Verify Stripe webhook signature via official SDK.
    Returns parsed event dict. Raises AuthError on failure.
    Stripe's 5-minute timestamp tolerance is enforced by the SDK.
    """
    try:
        event = stripe.Webhook.construct_event(raw_body, sig_header, webhook_secret)
        return dict(event)
    except stripe.SignatureVerificationError as exc:
        logger.warning("Stripe signature verification failed: %s", exc)
        raise AuthError("Invalid Stripe webhook signature.") from exc
    except Exception as exc:
        logger.error("Stripe webhook parse error: %s", exc)
        raise AuthError("Malformed Stripe webhook payload.") from exc


def verify_revenuecat_signature(
    authorization_header: str,
    webhook_secret: str,
) -> bool:
    """
    RevenueCat sends a static bearer token in Authorization header.
    Constant-time compare to prevent timing attacks.
    """
    return hmac.compare_digest(
        authorization_header.strip(),
        webhook_secret.strip(),
    )


# ---------------------------------------------------------------------------
# Ledger insert (idempotency gate)
# ---------------------------------------------------------------------------


async def insert_ledger_event(
    db: AsyncSession,
    provider: str,
    provider_event_id: str,
    event_type: str,
    event_timestamp: datetime,
    payload: dict[str, Any],
    signature_valid: bool,
) -> tuple[int | None, bool]:
    """
    Insert into WebhookEventLedger.
    Returns (ledger_id, is_new). If is_new=False, the event is a duplicate; skip.
    """
    stmt = (
        pg_insert(WebhookEventLedger)
        .values(
            provider=provider,
            provider_event_id=provider_event_id,
            event_type=event_type,
            event_timestamp=event_timestamp,
            payload=payload,
            signature_valid=signature_valid,
            status="received",
            attempts=0,
            received_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(constraint="uq_wel_provider_event")
        .returning(WebhookEventLedger.id)
    )
    result = await db.execute(stmt)
    await db.flush()
    row = result.fetchone()
    if row is None:
        # Duplicate
        logger.info("Duplicate %s event %s — skipping", provider, provider_event_id)
        return None, False
    return row[0], True


# ---------------------------------------------------------------------------
# Stripe event dispatch
# ---------------------------------------------------------------------------


async def dispatch_stripe_event(
    db: AsyncSession,
    ledger_id: int,
    event: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """Route a Stripe event to the appropriate handler."""
    from app.workers.stripe_handlers import (
        handle_checkout_completed,
        handle_sub_created,
        handle_sub_updated,
        handle_sub_canceled,
        handle_invoice_paid,
        handle_invoice_failed,
        handle_charge_refunded,
    )

    event_type = event.get("type", "")
    dispatch: dict[str, Any] = {
        "checkout.session.completed": handle_checkout_completed,
        "customer.subscription.created": handle_sub_created,
        "customer.subscription.updated": handle_sub_updated,
        "customer.subscription.deleted": handle_sub_canceled,
        "invoice.paid": handle_invoice_paid,
        "invoice.payment_failed": handle_invoice_failed,
        "charge.refunded": handle_charge_refunded,
    }
    handler = dispatch.get(event_type)
    if handler is None:
        logger.debug("Unhandled Stripe event type: %s", event_type)
        return

    await handler(db, event, amqp_channel, redis, settings)


# ---------------------------------------------------------------------------
# RevenueCat event dispatch
# ---------------------------------------------------------------------------


async def dispatch_rc_event(
    db: AsyncSession,
    ledger_id: int,
    event: dict[str, Any],
    amqp_channel: Any,
    redis: Any,
    settings: Any,
) -> None:
    """Route a RevenueCat event to the appropriate handler."""
    from app.workers.rc_handlers import (
        handle_rc_initial_purchase,
        handle_rc_renewal,
        handle_rc_cancellation,
        handle_rc_expiration,
        handle_rc_billing_issue,
        handle_rc_one_off,
        handle_rc_product_change,
        handle_rc_alias_merge,
    )

    event_type = event.get("type") or event.get("event", {}).get("type", "")
    dispatch: dict[str, Any] = {
        "INITIAL_PURCHASE": handle_rc_initial_purchase,
        "RENEWAL": handle_rc_renewal,
        "CANCELLATION": handle_rc_cancellation,
        "EXPIRATION": handle_rc_expiration,
        "BILLING_ISSUE": handle_rc_billing_issue,
        "NON_RENEWING_PURCHASE": handle_rc_one_off,
        "PRODUCT_CHANGE": handle_rc_product_change,
        "SUBSCRIBER_ALIAS": handle_rc_alias_merge,
    }
    handler = dispatch.get(event_type)
    if handler is None:
        logger.debug("Unhandled RC event type: %s", event_type)
        return

    await handler(db, event, amqp_channel, redis, settings)
