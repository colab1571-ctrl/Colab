"""0001 — create discovery schema + hide_3mo, saved_profiles, feed_preferences tables.

Revision ID: 0001
Revises:
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create discovery schema
    op.execute("CREATE SCHEMA IF NOT EXISTS discovery")

    # hide_3mo
    op.create_table(
        "hide_3mo",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("hidden_profile_id", UUID(as_uuid=True), nullable=False),
        sa.Column("hidden_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("hidden_until", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "hidden_profile_id", name="uq_hide3mo_user_profile"),
        schema="discovery",
    )
    op.create_index(
        "ix_hide3mo_user_until",
        "hide_3mo",
        ["user_id", "hidden_until"],
        schema="discovery",
    )

    # saved_profiles
    op.create_table(
        "saved_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("saved_profile_id", UUID(as_uuid=True), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "saved_profile_id", name="uq_saved_user_profile"),
        schema="discovery",
    )
    op.create_index(
        "ix_saved_user_at",
        "saved_profiles",
        ["user_id", sa.text("saved_at DESC")],
        schema="discovery",
    )

    # feed_preferences
    op.create_table(
        "feed_preferences",
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("mode", sa.String(10), nullable=False, server_default="scroll"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("mode IN ('scroll','swipe')", name="ck_feed_pref_mode"),
        schema="discovery",
    )


def downgrade() -> None:
    op.drop_table("feed_preferences", schema="discovery")
    op.drop_table("saved_profiles", schema="discovery")
    op.drop_table("hide_3mo", schema="discovery")
    op.execute("DROP SCHEMA IF EXISTS discovery CASCADE")
