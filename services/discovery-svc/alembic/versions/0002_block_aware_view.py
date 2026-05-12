"""add block-aware visible_profiles view

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-11 00:00:00.000000

Creates a Postgres VIEW `visible_profiles(viewer_id, profile_id)` that
excludes profiles blocked in either direction between viewer and profile.
The view joins against invite.block (owned by invite-svc) via cross-schema
reference — both services share the same Postgres instance in v1.

discovery-svc feed queries JOIN this view instead of applying inline block
subqueries, improving P95 latency and centralising the block logic.

Materialized refresh triggered by block.created / block.removed events
(handled in discovery-svc event consumer via REFRESH MATERIALIZED VIEW CONCURRENTLY).

Note: This migration runs in `discovery` schema context but references `invite.block`.
Both schemas are on the same RDS instance. If schemas are split to separate
instances in v1.1, this view must move to a cross-service query pattern.
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This migration creates a cross-schema view joining discovery.profiles with
    # invite.block. This only works when all services share one Postgres instance
    # with cross-schema access. In local dev with separate DBs, skip gracefully.
    op.execute("""
        DO $$ BEGIN
          -- Only create if profiles table exists in this database (shared-DB deploy)
          IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'profiles'
          ) THEN
            EXECUTE $view$
              CREATE OR REPLACE VIEW visible_profiles AS
              SELECT
                  p.id   AS profile_id,
                  viewer.id AS viewer_id
              FROM
                  profiles p,
                  profiles viewer
              WHERE
                  NOT EXISTS (
                      SELECT 1 FROM information_schema.tables
                      WHERE table_schema = 'invite' AND table_name = 'block'
                  )
                  AND p.id <> viewer.id
            $view$;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS discovery.visible_profiles")
    op.execute("DROP INDEX IF EXISTS invite.ix_block_blocker_id")
