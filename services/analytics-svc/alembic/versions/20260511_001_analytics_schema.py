"""analytics schema — events mirror table, KPIRollup

Revision ID: 20260511_001
Revises: None
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260511_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS analytics")

    # Events mirror (append-only by application convention)
    op.create_table(
        "events",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event", sa.String(128), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("props", JSONB, nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="analytics",
    )
    op.create_index("ix_events_ts", "events", ["ts"], schema="analytics")
    op.create_index("ix_events_user_ts", "events", ["user_id", "ts"], schema="analytics")
    op.create_index("ix_events_event_ts", "events", ["event", "ts"], schema="analytics")

    # KPI Rollup
    op.create_table(
        "kpi_rollup",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("day", sa.DateTime(timezone=True), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("dims", JSONB, nullable=False, server_default="{}"),
        sa.Column("value", sa.Numeric, nullable=True),
        sa.Column("count_n", sa.BigInteger, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("day", "key", "dims", name="uq_kpi_rollup_day_key_dims"),
        schema="analytics",
    )
    op.create_index(
        "ix_kpi_rollup_key_day", "kpi_rollup", ["key", "day"], schema="analytics"
    )


def downgrade() -> None:
    op.drop_table("kpi_rollup", schema="analytics")
    op.drop_table("events", schema="analytics")
    op.execute("DROP SCHEMA IF EXISTS analytics CASCADE")
