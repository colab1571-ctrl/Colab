"""
billing-svc — ORM models.

Tables (all in schema `billing`):
  Customer, Subscription, EntitlementSnapshot, CreditWallet,
  CreditTransaction, Invoice, RefundRequest, WebhookEventLedger, DunningCase.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from colab_common.db import Base


class Customer(Base):
    """Billing identity for a user. Created lazily on first checkout or webhook."""

    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_stripe_customer_id", "stripe_customer_id"),
        Index("ix_customers_country_currency", "country", "preferred_currency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    revenuecat_user_id: Mapped[str] = mapped_column(String(64), nullable=False)  # == user_id
    preferred_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="US")
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tax_id_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class Subscription(Base):
    """One row per platform per user. Multiple rows allowed for cross-platform."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "source IN ('stripe','revenuecat')", name="ck_sub_source",
        ),
        CheckConstraint(
            "gateway IN ('stripe','apple','google','paddle_in')", name="ck_sub_gateway",
        ),
        CheckConstraint(
            "tier IN ('free','premium','pro')", name="ck_sub_tier",
        ),
        CheckConstraint(
            "status IN ('trialing','active','past_due','grace','paused','canceled','expired')",
            name="ck_sub_status",
        ),
        CheckConstraint(
            "billing_period IN ('month','year')", name="ck_sub_period",
        ),
        Index("ix_sub_user_status", "user_id", "status"),
        Index("ix_sub_store_subscription_id", "store_subscription_id"),
        Index(
            "ix_sub_user_active",
            "user_id",
            postgresql_where="status IN ('trialing','active','past_due','grace')",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    gateway: Mapped[str] = mapped_column(String(16), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    store_subscription_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    store_product_id: Mapped[str] = mapped_column(String(256), nullable=False)
    billing_period: Mapped[str] = mapped_column(String(8), nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class EntitlementSnapshot(Base):
    """Per-user, per-axis entitlement value. Multiple sources allowed; precedence at read."""

    __tablename__ = "entitlement_snapshots"
    __table_args__ = (
        CheckConstraint(
            "source IN ('default','subscription','grant','promo','family_share')",
            name="ck_ent_source",
        ),
        UniqueConstraint("user_id", "axis_key", "source", "source_ref", name="uq_ent_user_axis_source"),
        Index("ix_ent_user_id", "user_id"),
        Index("ix_ent_expires_at", "expires_at", postgresql_where="expires_at IS NOT NULL"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    axis_key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    source_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class CreditWallet(Base):
    """Denormalized balance per user. Source of truth is CreditTransaction sum."""

    __tablename__ = "credit_wallets"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class CreditTransaction(Base):
    """Append-only credit ledger."""

    __tablename__ = "credit_transactions"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('purchase','admin_grant','subscription_grant','consume','reserve','release','refund','expire')",
            name="ck_ct_reason",
        ),
        CheckConstraint(
            "status IN ('reserved','committed','released','reversed')",
            name="ck_ct_status",
        ),
        UniqueConstraint("idempotency_key", name="uq_ct_idempotency_key"),
        Index("ix_ct_user_created", "user_id", "created_at"),
        Index("ix_ct_reserved", "status", postgresql_where="status='reserved'"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(256), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="committed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Invoice(Base):
    """Mirrors Stripe invoices; mobile invoices are informational."""

    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','open','paid','uncollectible','void','refunded','partial_refund')",
            name="ck_inv_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    stripe_invoice_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    rc_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    tax_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hosted_invoice_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class RefundRequest(Base):
    """Tracks all refund requests regardless of platform outcome."""

    __tablename__ = "refund_requests"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('subscription','credit_purchase')", name="ck_rr_kind",
        ),
        CheckConstraint(
            "status IN ('auto_approved','pending','approved','denied','routed_to_apple','routed_to_google')",
            name="ck_rr_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    within_14d: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason_user: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_internal: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    refund_amount_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    refund_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    stripe_refund_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class WebhookEventLedger(Base):
    """Idempotency store for all inbound provider webhooks."""

    __tablename__ = "webhook_event_ledger"
    __table_args__ = (
        CheckConstraint("provider IN ('stripe','revenuecat')", name="ck_wel_provider"),
        CheckConstraint(
            "status IN ('received','processing','done','retry','dead')",
            name="ck_wel_status",
        ),
        UniqueConstraint("provider", "provider_event_id", name="uq_wel_provider_event"),
        Index(
            "ix_wel_status_received",
            "status",
            "received_at",
            postgresql_where="status IN ('received','retry')",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="received")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DunningCase(Base):
    """State machine row tracking dunning progress per subscription."""

    __tablename__ = "dunning_cases"
    __table_args__ = (
        CheckConstraint(
            "state IN ('day0','day3','day7','day10_canceled','day30_grace_expired','recovered')",
            name="ck_dc_state",
        ),
        Index("ix_dc_state_opened", "state", "opened_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
