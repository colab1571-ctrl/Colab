"""create waitlist_emails table (017 marketing-web integration)

Revision ID: 0001_create_waitlist_emails
Revises:
Create Date: 2026-05-11

Cross-service note:
  This table is owned by the marketing-web integration surface (spec 017).
  It lives in gateway-svc schema because:
    a) gateway-svc is the only deployed service with a DB connection at P16, and
    b) a dedicated marketing-svc is not planned until post-launch.

  If a marketing-svc or notification-svc is created in future, this table
  migrates there via a schema-transfer migration. The API contract
  (POST /api/waitlist) remains unchanged.

Entity: WaitlistEmail
  - id          UUID PK
  - email       TEXT UNIQUE NOT NULL
  - source      TEXT NOT NULL DEFAULT 'homepage'  -- which page/CTA the signup came from
  - consent_at  TIMESTAMPTZ NULL                  -- CASL explicit consent timestamp
  - ip_hashed   TEXT NULL                         -- SHA-256 of raw IP (one-way hash)
  - created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_create_waitlist_emails"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "waitlist_emails",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.Text, unique=True, nullable=False),
        sa.Column("source", sa.Text, nullable=False, server_default="homepage"),
        sa.Column("consent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ip_hashed", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Index for deduplication queries by email
    op.create_index(
        "ix_waitlist_emails_email",
        "waitlist_emails",
        ["email"],
        unique=True,
    )

    # Index for time-based analytics queries
    op.create_index(
        "ix_waitlist_emails_created_at",
        "waitlist_emails",
        ["created_at"],
    )

    # Index for source funnel analysis
    op.create_index(
        "ix_waitlist_emails_source",
        "waitlist_emails",
        ["source"],
    )


def downgrade() -> None:
    op.drop_index("ix_waitlist_emails_source", table_name="waitlist_emails")
    op.drop_index("ix_waitlist_emails_created_at", table_name="waitlist_emails")
    op.drop_index("ix_waitlist_emails_email", table_name="waitlist_emails")
    op.drop_table("waitlist_emails")
