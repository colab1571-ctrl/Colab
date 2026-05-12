"""initial auth schema

Revision ID: 0001
Revises:
Create Date: 2026-05-11 00:00:00.000000

Creates: users, identities, sessions, legal_acceptances, magic_links, event_outbox
Indexes per plan §4 data model.
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
    # Enums
    op.execute(
        "CREATE TYPE email_status_enum AS ENUM ('active', 'bounced', 'complained')"
    )
    op.execute(
        "CREATE TYPE identity_provider_enum AS ENUM ('apple', 'google', 'email', 'phone')"
    )
    op.execute(
        "CREATE TYPE doc_type_enum AS ENUM ('tos', 'privacy', 'community_guidelines')"
    )
    op.execute(
        "CREATE TYPE magic_link_purpose_enum AS ENUM "
        "('email_verify', 'password_reset', 'email_change', 'phone_change')"
    )

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_status", sa.Enum(name="email_status_enum", create_type=False), nullable=False, server_default="active"),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_hash", sa.Text, nullable=True),
        sa.Column("password_hash_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_locked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("mfa_secret", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)

    # identities
    op.create_table(
        "identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Enum(name="identity_provider_enum", create_type=False), nullable=False),
        sa.Column("provider_subject", sa.String(512), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_identities_user_id", "identities", ["user_id"])
    op.create_unique_constraint("uq_identities_provider_subject", "identities", ["provider", "provider_subject"])

    # sessions
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False),
        sa.Column("refresh_jti", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_refresh_token_hash", "sessions", ["refresh_token_hash"], unique=True)
    op.create_index("ix_sessions_refresh_jti", "sessions", ["refresh_jti"], unique=True)

    # legal_acceptances
    op.create_table(
        "legal_acceptances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doc_type", sa.Enum(name="doc_type_enum", create_type=False), nullable=False),
        sa.Column("doc_version", sa.String(32), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ip", sa.String(45), nullable=True),
    )
    op.create_index("ix_legal_acceptances_user_id", "legal_acceptances", ["user_id"])

    # magic_links
    op.create_table(
        "magic_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.Enum(name="magic_link_purpose_enum", create_type=False), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("otp_hash", sa.String(64), nullable=True),
        sa.Column("new_value", sa.String(255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_magic_links_token_hash", "magic_links", ["token_hash"], unique=True)

    # event_outbox (shared pattern from colab_common)
    op.create_table(
        "event_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("event_name", sa.String(255), nullable=False),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("dedupe_key", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_attempts", sa.String(10), nullable=True, server_default="0"),
    )
    op.create_index("ix_event_outbox_event_name", "event_outbox", ["event_name"])
    op.create_unique_constraint("uq_event_outbox_dedupe_key", "event_outbox", ["dedupe_key"])


def downgrade() -> None:
    op.drop_table("event_outbox")
    op.drop_table("magic_links")
    op.drop_table("legal_acceptances")
    op.drop_table("sessions")
    op.drop_table("identities")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS magic_link_purpose_enum")
    op.execute("DROP TYPE IF EXISTS doc_type_enum")
    op.execute("DROP TYPE IF EXISTS identity_provider_enum")
    op.execute("DROP TYPE IF EXISTS email_status_enum")
