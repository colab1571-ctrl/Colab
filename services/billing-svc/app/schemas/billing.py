"""
billing-svc — Pydantic request/response schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Entitlements
# ---------------------------------------------------------------------------


class EntitlementsResponse(BaseModel):
    axes: dict[str, Any]
    tier: Literal["free", "premium", "pro"]
    subscription_status: str | None = None
    current_period_end: datetime | None = None


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------


class SubscriptionOut(BaseModel):
    id: uuid.UUID
    source: str
    gateway: str
    tier: str
    status: str
    billing_period: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    trial_end: datetime | None = None
    started_at: datetime
    canceled_at: datetime | None = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------


class CheckoutWebRequest(BaseModel):
    price_id: str = Field(..., description="Stripe Price ID — must be in allowed allowlist")
    return_url: str
    cancel_url: str | None = None


class CheckoutWebResponse(BaseModel):
    checkout_url: str
    session_id: str


# ---------------------------------------------------------------------------
# Credits
# ---------------------------------------------------------------------------


class CreditBalanceResponse(BaseModel):
    balance: int


class CreditPurchaseWebRequest(BaseModel):
    price_id: str
    return_url: str


class ReserveCreditsRequest(BaseModel):
    user_id: uuid.UUID
    amount: int = Field(..., gt=0)
    reference_kind: str
    reference_id: str
    idempotency_key: str | None = None


class ReserveCreditsResponse(BaseModel):
    reservation_id: uuid.UUID


class CommitCreditsRequest(BaseModel):
    reservation_id: uuid.UUID


class ReleaseCreditsRequest(BaseModel):
    reservation_id: uuid.UUID
    reason: str = "release"


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


class CancelWebRequest(BaseModel):
    subscription_id: uuid.UUID
    immediate: bool = False


# ---------------------------------------------------------------------------
# Refund
# ---------------------------------------------------------------------------


class RefundRequestCreate(BaseModel):
    subscription_id: uuid.UUID | None = None
    transaction_id: uuid.UUID | None = None
    reason: str | None = None


class RefundRequestOut(BaseModel):
    refund_request_id: uuid.UUID
    status: str
    refund_amount_minor: int | None = None
    currency: str | None = None
    routed_to: Literal["apple", "google"] | None = None


class AdminRefundDecide(BaseModel):
    decision: Literal["approve", "deny"]
    internal_note: str | None = None


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


class AdminGrantRequest(BaseModel):
    user_id: uuid.UUID
    axis_key: str
    value: Any
    expires_at: datetime | None = None
    reason: str


class AdminCreditAdjustment(BaseModel):
    user_id: uuid.UUID
    delta: int
    reason: str


class AdminTierConfigUpdate(BaseModel):
    tier: Literal["free", "premium", "pro"]
    axis_key: str
    value: Any
