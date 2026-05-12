"""initial invite schema

Revision ID: 0001
Revises:
Create Date: 2026-05-11 00:00:00.000000

Creates:
  collab_invite  — Vibe Check invite rows (never deleted; terminal states archived)
  block          — Bidirectional block registry

Indexes per plan §3:
  - collab_invite: inbox query, sent query, TTL job (partial on pending)
  - block: reverse lookup (blocked_id)

CHECK constraints enforce status enum and synopsis length without a DB ENUM type
(colab convention: text + CHECK for portability and zero migration cost on additions).
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
    # collab_invite
    # ------------------------------------------------------------------
    op.create_table(
        "collab_invite",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("from_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("synopsis", sa.String(250), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("ai_match_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("mod_case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archive_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True, unique=True),
        # Integrity constraints
        sa.CheckConstraint(
            "status IN ('pending','accepted','rejected','expired','cancelled')",
            name="ck_invite_status",
        ),
        sa.CheckConstraint(
            "char_length(synopsis) <= 250",
            name="ck_invite_synopsis_len",
        ),
        sa.CheckConstraint(
            "from_profile_id <> to_profile_id",
            name="ck_invite_no_self_invite",
        ),
        sa.CheckConstraint(
            "ai_match_score IS NULL OR (ai_match_score >= 0 AND ai_match_score <= 1)",
            name="ck_invite_ai_score_range",
        ),
    )

    # Inbox query: recipient + status + recency
    op.create_index(
        "ix_invite_to_status_created",
        "collab_invite",
        ["to_profile_id", "status", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )
    # Sent query: sender + status + recency
    op.create_index(
        "ix_invite_from_status_created",
        "collab_invite",
        ["from_profile_id", "status", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )
    # TTL Celery Beat job: only pending rows with archive_at in the past
    op.create_index(
        "ix_invite_ttl_job",
        "collab_invite",
        ["status", "archive_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    # Idempotency key lookup
    op.create_index(
        "ix_invite_idempotency_key",
        "collab_invite",
        ["idempotency_key"],
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # ------------------------------------------------------------------
    # block
    # ------------------------------------------------------------------
    op.create_table(
        "block",
        sa.Column("blocker_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("blocked_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("reason", sa.String(32), nullable=True),
        sa.CheckConstraint(
            "reason IS NULL OR reason IN ('harassment','spam','inappropriate_content','other')",
            name="ck_block_reason",
        ),
        sa.CheckConstraint(
            "blocker_id <> blocked_id",
            name="ck_block_no_self_block",
        ),
    )

    # Reverse lookup: is user X blocked by anyone?
    op.create_index("ix_block_blocked_id", "block", ["blocked_id"])

    # ------------------------------------------------------------------
    # event_outbox (shared transactional outbox pattern)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS event_outbox (
            id           BIGSERIAL PRIMARY KEY,
            routing_key  TEXT NOT NULL,
            payload      JSONB NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            published    BOOLEAN NOT NULL DEFAULT false,
            published_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_outbox_unpublished
        ON event_outbox (created_at)
        WHERE published = false
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS event_outbox")
    op.drop_index("ix_block_blocked_id", table_name="block")
    op.drop_table("block")
    op.drop_index("ix_invite_idempotency_key", table_name="collab_invite")
    op.drop_index("ix_invite_ttl_job", table_name="collab_invite")
    op.drop_index("ix_invite_from_status_created", table_name="collab_invite")
    op.drop_index("ix_invite_to_status_created", table_name="collab_invite")
    op.drop_table("collab_invite")
