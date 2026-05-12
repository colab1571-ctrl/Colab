"""admin schema — AdminUser, AdminAuditLog (append-only), FeatureFlag, EntitlementConfig

Revision ID: 20260511_001
Revises: None
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID

revision = "20260511_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create admin schema
    op.execute("CREATE SCHEMA IF NOT EXISTS admin")

    # AdminUser
    op.create_table(
        "admin_user",
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("roles", ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_enrolled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_secret", sa.Text, nullable=True),
        schema="admin",
    )
    op.create_index(
        "ix_admin_user_roles", "admin_user", ["roles"],
        schema="admin", postgresql_using="gin",
    )

    # AdminAuditLog (append-only)
    op.create_table(
        "admin_audit_log",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("admin_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("target_kind", sa.String(64), nullable=False),
        sa.Column("target_id", sa.Text, nullable=False),
        sa.Column("payload_before", JSONB, nullable=True),
        sa.Column("payload_after", JSONB, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("ip", INET, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="admin",
    )
    op.create_index(
        "ix_aal_admin_user_created",
        "admin_audit_log",
        ["admin_user_id", "created_at"],
        schema="admin",
    )
    op.create_index(
        "ix_aal_target",
        "admin_audit_log",
        ["target_kind", "target_id", "created_at"],
        schema="admin",
    )
    op.create_index(
        "ix_aal_action_created",
        "admin_audit_log",
        ["action_type", "created_at"],
        schema="admin",
    )

    # Append-only enforcement: REVOKE mutating privileges + trigger
    op.execute(
        "REVOKE UPDATE, DELETE, TRUNCATE ON admin.admin_audit_log FROM PUBLIC"
    )
    op.execute("""
        CREATE OR REPLACE FUNCTION admin.audit_log_no_mutate()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'admin.admin_audit_log is append-only';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_audit_log_no_mutate
        BEFORE UPDATE OR DELETE OR TRUNCATE
        ON admin.admin_audit_log
        FOR EACH STATEMENT EXECUTE FUNCTION admin.audit_log_no_mutate()
    """)

    # FeatureFlag
    op.create_table(
        "feature_flag",
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("env", sa.String(16), nullable=False),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("canary_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("key", "env"),
        schema="admin",
    )

    # EntitlementConfig
    op.create_table(
        "entitlement_config",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tier", sa.String(32), nullable=False),
        sa.Column("axis_key", sa.String(64), nullable=False),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column(
            "effective_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tier", "axis_key", "effective_at",
            name="uq_entitlement_tier_axis_effective",
        ),
        schema="admin",
    )
    op.create_index(
        "ix_entitlement_tier_axis",
        "entitlement_config",
        ["tier", "axis_key"],
        schema="admin",
    )

    # Casbin rule table (used by casbin_sqlalchemy_adapter)
    op.create_table(
        "casbin_rule",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ptype", sa.String(255), nullable=True),
        sa.Column("v0", sa.String(255), nullable=True),
        sa.Column("v1", sa.String(255), nullable=True),
        sa.Column("v2", sa.String(255), nullable=True),
        sa.Column("v3", sa.String(255), nullable=True),
        sa.Column("v4", sa.String(255), nullable=True),
        sa.Column("v5", sa.String(255), nullable=True),
        schema="admin",
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_mutate ON admin.admin_audit_log")
    op.execute("DROP FUNCTION IF EXISTS admin.audit_log_no_mutate()")
    op.drop_table("casbin_rule", schema="admin")
    op.drop_table("entitlement_config", schema="admin")
    op.drop_table("feature_flag", schema="admin")
    op.drop_table("admin_audit_log", schema="admin")
    op.drop_table("admin_user", schema="admin")
    op.execute("DROP SCHEMA IF EXISTS admin CASCADE")
