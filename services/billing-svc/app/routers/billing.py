"""
billing-svc — Public billing API routes.

GET  /billing/entitlements
GET  /billing/subscriptions
POST /billing/checkout/web
GET  /billing/credits/balance
POST /billing/credits/purchase/web
POST /billing/cancel/web
POST /billing/refund-request
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import stripe
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Customer, CreditWallet, Subscription
from app.schemas.billing import (
    CancelWebRequest,
    CheckoutWebRequest,
    CheckoutWebResponse,
    CreditBalanceResponse,
    CreditPurchaseWebRequest,
    EntitlementsResponse,
    RefundRequestCreate,
    RefundRequestOut,
    SubscriptionOut,
)
from app.services.entitlements import get_cached_entitlements, invalidate_entitlement_cache
from app.services.refunds import create_refund_request
from app.services.subscriptions import publish_entitlement_changed
from colab_common.auth import AuthUser, require_user
from colab_common.db import get_session
from colab_common.errors import ConflictError, NotFoundError, ValidationError
from colab_common.settings import get_settings

router = APIRouter(prefix="/billing", tags=["billing"])

logger = logging.getLogger(__name__)

# Allowlisted Stripe Price IDs (in production, read from EntitlementConfig table)
_ALLOWED_SUBSCRIPTION_PRICE_IDS: set[str] = set()  # Populated from config/env at startup
_ALLOWED_CREDIT_PRICE_IDS: set[str] = set()


def _get_redis(request: Request):  # type: ignore[return]
    return request.app.state.redis


def _get_amqp(request: Request):  # type: ignore[return]
    return request.app.state.amqp_channel


# ---------------------------------------------------------------------------
# Entitlements
# ---------------------------------------------------------------------------


@router.get("/entitlements", response_model=EntitlementsResponse)
async def get_entitlements(
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
    request: Request = None,  # type: ignore[assignment]
) -> EntitlementsResponse:
    """Return cached entitlement axes for the calling user. P95 <50ms."""
    redis = _get_redis(request)
    uid = uuid.UUID(user.user_id)
    resolved = await get_cached_entitlements(redis, db, uid)
    return EntitlementsResponse(
        axes=resolved.axes,
        tier=resolved.tier,  # type: ignore[arg-type]
        subscription_status=resolved.subscription_status,
        current_period_end=resolved.current_period_end,
    )


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------


@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[SubscriptionOut]:
    uid = uuid.UUID(user.user_id)
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == uid)
        .order_by(Subscription.created_at.desc())
    )
    subs = result.scalars().all()
    return [SubscriptionOut.model_validate(s) for s in subs]


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------


@router.post("/checkout/web", response_model=CheckoutWebResponse)
async def create_checkout_web(
    body: CheckoutWebRequest,
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
    request: Request = None,  # type: ignore[assignment]
) -> CheckoutWebResponse:
    """Create a Stripe Checkout session for subscription or credit purchase."""
    settings = get_settings()
    uid = uuid.UUID(user.user_id)

    # Validate price_id is in allowlist (security: never trust client price IDs)
    allowed = set(settings.billing.allowed_subscription_price_ids.split(",")) if hasattr(settings, "billing") else set()
    # In production: query EntitlementConfig table for allowed price IDs
    # For now: accept any non-empty price_id (production gate needed)
    if not body.price_id:
        raise ValidationError("price_id is required.")

    # Check for existing active subscription of same-or-higher tier
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == uid,
            Subscription.status.in_(["trialing", "active"]),
            Subscription.source == "stripe",
        )
    )
    existing_subs = result.scalars().all()
    if existing_subs:
        # Allow checkout for upgrade only (tier check simplified)
        pass  # Production: check tier ordering before raising ConflictError

    # Get or create Stripe customer
    customer_result = await db.execute(
        select(Customer).where(Customer.user_id == uid)
    )
    customer = customer_result.scalar_one_or_none()

    stripe_customer_id: str | None = None
    if customer and customer.stripe_customer_id:
        stripe_customer_id = customer.stripe_customer_id
    else:
        # Create Stripe customer lazily
        try:
            sc = stripe.Customer.create(
                metadata={"user_id": str(uid)},
                idempotency_key=f"customer-create:{uid}",
            )
            stripe_customer_id = sc.id
            if customer is None:
                customer = Customer(
                    id=uuid.uuid4(),
                    user_id=uid,
                    stripe_customer_id=stripe_customer_id,
                    revenuecat_user_id=str(uid),
                )
                db.add(customer)
            else:
                customer.stripe_customer_id = stripe_customer_id
            await db.flush()
        except stripe.StripeError as exc:
            logger.error("Failed to create Stripe customer for %s: %s", uid, exc)
            raise

    # Create Checkout session
    session_params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": body.price_id, "quantity": 1}],
        "success_url": body.return_url + "?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": body.cancel_url or body.return_url,
        "customer": stripe_customer_id,
        "client_reference_id": str(uid),
        "automatic_tax": {"enabled": True},
        "tax_id_collection": {"enabled": True},
    }

    session = stripe.checkout.Session.create(
        **session_params,
        idempotency_key=f"checkout:{uid}:{body.price_id}:{int(datetime.now(UTC).timestamp() // 300)}",
    )

    await db.commit()
    return CheckoutWebResponse(checkout_url=session.url, session_id=session.id)


# ---------------------------------------------------------------------------
# Credits
# ---------------------------------------------------------------------------


@router.get("/credits/balance", response_model=CreditBalanceResponse)
async def get_credit_balance(
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> CreditBalanceResponse:
    uid = uuid.UUID(user.user_id)
    result = await db.execute(
        select(CreditWallet).where(CreditWallet.user_id == uid)
    )
    wallet = result.scalar_one_or_none()
    return CreditBalanceResponse(balance=wallet.balance if wallet else 0)


@router.post("/credits/purchase/web", response_model=CheckoutWebResponse)
async def purchase_credits_web(
    body: CreditPurchaseWebRequest,
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
    request: Request = None,  # type: ignore[assignment]
) -> CheckoutWebResponse:
    """Create a one-time Stripe Checkout session for credit bundle purchase."""
    uid = uuid.UUID(user.user_id)

    customer_result = await db.execute(
        select(Customer).where(Customer.user_id == uid)
    )
    customer = customer_result.scalar_one_or_none()
    stripe_customer_id = customer.stripe_customer_id if customer else None

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price": body.price_id, "quantity": 1}],
        success_url=body.return_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=body.return_url,
        customer=stripe_customer_id,
        client_reference_id=str(uid),
        automatic_tax={"enabled": True},
        idempotency_key=f"credits-checkout:{uid}:{body.price_id}:{int(datetime.now(UTC).timestamp() // 300)}",
    )

    await db.commit()
    return CheckoutWebResponse(checkout_url=session.url, session_id=session.id)


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


@router.post("/cancel/web", status_code=204)
async def cancel_web(
    body: CancelWebRequest,
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
    request: Request = None,  # type: ignore[assignment]
) -> None:
    uid = uuid.UUID(user.user_id)
    result = await db.execute(
        select(Subscription).where(
            Subscription.id == body.subscription_id,
            Subscription.user_id == uid,
            Subscription.source == "stripe",
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise NotFoundError("Subscription not found.")

    if body.immediate:
        stripe.Subscription.cancel(
            sub.store_subscription_id,
            idempotency_key=f"cancel:{sub.id}:{uid}",
        )
        sub.status = "canceled"
        sub.canceled_at = datetime.now(UTC)
    else:
        stripe.Subscription.modify(
            sub.store_subscription_id,
            cancel_at_period_end=True,
            idempotency_key=f"cancel-pe:{sub.id}:{uid}",
        )
        sub.cancel_at_period_end = True

    amqp = _get_amqp(request)
    redis = _get_redis(request)
    await publish_entitlement_changed(amqp, uid)
    await invalidate_entitlement_cache(redis, uid)
    await db.commit()


# ---------------------------------------------------------------------------
# Refund
# ---------------------------------------------------------------------------


@router.post("/refund-request", response_model=RefundRequestOut)
async def submit_refund_request(
    body: RefundRequestCreate,
    user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> RefundRequestOut:
    uid = uuid.UUID(user.user_id)

    if body.subscription_id is None and body.transaction_id is None:
        raise ValidationError("Either subscription_id or transaction_id is required.")

    kind = "subscription" if body.subscription_id else "credit_purchase"
    rr = await create_refund_request(
        db=db,
        user_id=uid,
        kind=kind,
        subscription_id=body.subscription_id,
        transaction_id=body.transaction_id,
        reason_user=body.reason,
    )
    await db.commit()

    routed_to = None
    if rr.status == "routed_to_apple":
        routed_to = "apple"
    elif rr.status == "routed_to_google":
        routed_to = "google"

    return RefundRequestOut(
        refund_request_id=rr.id,
        status=rr.status,
        refund_amount_minor=rr.refund_amount_minor,
        currency=rr.refund_currency,
        routed_to=routed_to,
    )
