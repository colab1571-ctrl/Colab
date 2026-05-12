"""0001 — enable postgis, vector, citext, pg_trgm extensions.

Revision ID: 0001
Revises:
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostGIS — optional; skip if not installed (pgvector-only image in local dev)
    op.execute(
        "DO $$ BEGIN "
        "  CREATE EXTENSION IF NOT EXISTS postgis; "
        "EXCEPTION WHEN OTHERS THEN "
        "  RAISE NOTICE 'PostGIS not available, skipping (local dev mode)'; "
        "END $$;"
    )
    # pgvector — for embedding similarity search
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")


def downgrade() -> None:
    # Extensions are shared; do not drop in downgrade
    pass
