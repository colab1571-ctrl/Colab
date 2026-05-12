"""initial billing schema

Revision ID: 0001
Revises:
Create Date: 2026-05-11 00:00:00.000000

Creates: customers, subscriptions, entitlement_snapshots, credit_wallets,
         credit_transactions, invoices, refund_requests, webhook_event_ledger,
         dunning_cases, event_outbox (shared).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # customers
    # ------------------------------------------------------------------
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stripe_customer_id", sa.String(64), nullable=True),
        sa.Column("revenuecat_user_id", sa.String(64), nullable=False),
        sa.Column("preferred_currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("country", sa.String(2), nullable=False, server_default="US"),
        sa.Column("tax_id", sa.String(64), nullable=True),
        sa.Column("tax_id_type", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", name="uq_customers_user_id"),
        sa.UniqueConstraint("stripe_customer_id", name="uq_customers_stripe_id"),
    )
    op.create_index("ix_customers_stripe_customer_id", "customers", ["stripe_customer_id"])
    op.create_index("ix_customers_country_currency", "customers", ["country", "preferred_currency"])

    # ------------------------------------------------------------------
    # subscriptions
    # ------------------------------------------------------------------
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("gateway", sa.String(16), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("store_subscription_id", sa.String(256), nullable=True),
        sa.Column("store_product_id", sa.String(256), nullable=False),
        sa.Column("billing_period", sa.String(8), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancel_at_period_end", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_reason", sa.String(32), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="'{}'"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("source IN ('stripe','revenuecat')", name="ck_sub_source"),
        sa.CheckConstraint("gateway IN ('stripe','apple','google','paddle_in')", name="ck_sub_gateway"),
        sa.CheckConstraint("tier IN ('free','premium','pro')", name="ck_sub_tier"),
        sa.CheckConstraint(
            "status IN ('trialing','active','past_due','grace','paused','canceled','expired')",
            name="ck_sub_status",
        ),
        sa.CheckConstraint("billing_period IN ('month','year')", name="ck_sub_period"),
    )
    op.create_index("ix_sub_user_status", "subscriptions", ["user_id", "status"])
    op.create_index("ix_sub_store_subscription_id", "subscriptions", ["store_subscription_id"])
    op.create_index(
        "ix_sub_user_active",
        "subscriptions",
        ["user_id"],
        postgresql_where=sa.text("status IN ('trialing','active','past_due','grace')"),
    )

    # ------------------------------------------------------------------
    # entitlement_snapshots
    # ------------------------------------------------------------------
    op.create_table(
        "entitlement_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("axis_key", sa.String(64), nullable=False),
        sa.Column("value", postgresql.JSONB, nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_ref", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "source IN ('default','subscription','grant','promo','family_share')",
            name="ck_ent_source",
        ),
        sa.UniqueConstraint("user_id", "axis_key", "source", "source_ref", name="uq_ent_user_axis_source"),
    )
    op.create_index("ix_ent_user_id", "entitlement_snapshots", ["user_id"])
    op.create_index(
        "ix_ent_expires_at",
        "entitlement_snapshots",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )

    # ------------------------------------------------------------------
    # credit_wallets
    # ------------------------------------------------------------------
    op.create_table(
        "credit_wallets",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("balance", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------
    # credit_transactions
    # ------------------------------------------------------------------
    op.create_table(
        "credit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delta", sa.BigInteger, nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("reference_kind", sa.String(32), nullable=False),
        sa.Column("reference_id", sa.String(256), nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="committed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "reason IN ('purchase','admin_grant','subscription_grant','consume','reserve','release','refund','expire')",
            name="ck_ct_reason",
        ),
        sa.CheckConstraint(
            "status IN ('reserved','committed','released','reversed')",
            name="ck_ct_status",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_ct_idempotency_key"),
    )
    op.create_index("ix_ct_user_created", "credit_transactions", ["user_id", "created_at"])
    op.create_index(
        "ix_ct_reserved",
        "credit_transactions",
        ["status"],
        postgresql_where=sa.text("status='reserved'"),
    )

    # ------------------------------------------------------------------
    # invoices
    # ------------------------------------------------------------------
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stripe_invoice_id", sa.String(64), nullable=True),
        sa.Column("rc_event_id", sa.String(128), nullable=True),
        sa.Column("amount_minor", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("tax_minor", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hosted_invoice_url", sa.Text, nullable=True),
        sa.Column("pdf_url", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('draft','open','paid','uncollectible','void','refunded','partial_refund')",
            name="ck_inv_status",
        ),
        sa.UniqueConstraint("stripe_invoice_id", name="uq_invoices_stripe_id"),
        sa.UniqueConstraint("rc_event_id", name="uq_invoices_rc_event_id"),
    )

    # ------------------------------------------------------------------
    # refund_requests
    # ------------------------------------------------------------------
    op.create_table(
        "refund_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("within_14d", sa.Boolean, nullable=False),
        sa.Column("reason_user", sa.Text, nullable=True),
        sa.Column("reason_internal", sa.Text, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("refund_amount_minor", sa.BigInteger, nullable=True),
        sa.Column("refund_currency", sa.String(3), nullable=True),
        sa.Column("stripe_refund_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("kind IN ('subscription','credit_purchase')", name="ck_rr_kind"),
        sa.CheckConstraint(
            "status IN ('auto_approved','pending','approved','denied','routed_to_apple','routed_to_google')",
            name="ck_rr_status",
        ),
    )

    # ------------------------------------------------------------------
    # webhook_event_ledger
    # ------------------------------------------------------------------
    op.create_table(
        "webhook_event_ledger",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("provider_event_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("signature_valid", sa.Boolean, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="received"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("provider IN ('stripe','revenuecat')", name="ck_wel_provider"),
        sa.CheckConstraint(
            "status IN ('received','processing','done','retry','dead')",
            name="ck_wel_status",
        ),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_wel_provider_event"),
    )
    op.create_index(
        "ix_wel_status_received",
        "webhook_event_ledger",
        ["status", "received_at"],
        postgresql_where=sa.text("status IN ('received','retry')"),
    )

    # ------------------------------------------------------------------
    # dunning_cases
    # ------------------------------------------------------------------
    op.create_table(
        "dunning_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_result", sa.Text, nullable=True),
        sa.Column("last_email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('day0','day3','day7','day10_canceled','day30_grace_expired','recovered')",
            name="ck_dc_state",
        ),
    )
    op.create_index("ix_dc_state_opened", "dunning_cases", ["state", "opened_at"])

    # ------------------------------------------------------------------
    # event_outbox (shared pattern from colab_common)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS event_outbox (
            id          BIGSERIAL PRIMARY KEY,
            routing_key TEXT NOT NULL,
            payload     JSONB NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            published   BOOLEAN NOT NULL DEFAULT false,
            published_at TIMESTAMPTZ
        )
    """)


def downgrade() -> None:
    op.drop_table("dunning_cases")
    op.drop_table("webhook_event_ledger")
    op.drop_table("refund_requests")
    op.drop_table("invoices")
    op.drop_table("credit_transactions")
    op.drop_table("credit_wallets")
    op.drop_table("entitlement_snapshots")
    op.drop_table("subscriptions")
    op.drop_table("customers")
    op.execute("DROP TABLE IF EXISTS event_outbox")
