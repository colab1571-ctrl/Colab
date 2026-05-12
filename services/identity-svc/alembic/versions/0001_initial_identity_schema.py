"""initial identity schema

Revision ID: 0001
Revises:
Create Date: 2026-05-11 00:00:00.000000

Creates: identity_verifications, persona_webhook_events, event_outbox
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
    op.execute(
        "CREATE TYPE identity_status_enum AS ENUM ('pending', 'approved', 'declined', 'needs_review')"
    )

    op.create_table(
        "identity_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("persona_inquiry_id", sa.String(255), nullable=True),
        sa.Column("status", sa.Enum(name="identity_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("face_age_signal", sa.String(32), nullable=True),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_identity_verifications_user_id", "identity_verifications", ["user_id"])
    op.create_index("ix_identity_verifications_persona_inquiry_id", "identity_verifications", ["persona_inquiry_id"])

    op.create_table(
        "persona_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("event_name", sa.String(128), nullable=False),
        sa.Column("inquiry_id", sa.String(255), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("raw_payload", postgresql.JSONB, nullable=True),
    )
    op.create_unique_constraint("uq_persona_webhook_event_id", "persona_webhook_events", ["event_id"])

    # event_outbox
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
    op.drop_table("persona_webhook_events")
    op.drop_table("identity_verifications")
    op.execute("DROP TYPE IF EXISTS identity_status_enum")
