"""0006 — webhook_receipts idempotency table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_receipts",
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("provider", "external_id", name="pk_webhook_receipts"),
    )


def downgrade() -> None:
    op.drop_table("webhook_receipts")
