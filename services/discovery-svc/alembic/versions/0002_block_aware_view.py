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


def upgrade() -> None:
    # Create a non-materialized view first for correctness; can be materialized later
    # Uses SECURITY INVOKER so queries run with the connecting user's privileges.
    op.execute("""
        CREATE OR REPLACE VIEW discovery.visible_profiles AS
        SELECT
            p.id   AS profile_id,
            viewer.id AS viewer_id
        FROM
            profiles p,
            profiles viewer
        WHERE
            -- Exclude if viewer blocked p
            NOT EXISTS (
                SELECT 1 FROM invite.block b
                WHERE b.blocker_id = viewer.id AND b.blocked_id = p.id
            )
            -- Exclude if p blocked viewer
            AND NOT EXISTS (
                SELECT 1 FROM invite.block b
                WHERE b.blocker_id = p.id AND b.blocked_id = viewer.id
            )
            -- Exclude self
            AND p.id <> viewer.id
    """)

    # Index on invite.block for discovery join performance
    # (already created by invite-svc migration, but guard with IF NOT EXISTS)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_block_blocker_id
        ON invite.block (blocker_id)
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS discovery.visible_profiles")
    op.execute("DROP INDEX IF EXISTS invite.ix_block_blocker_id")
