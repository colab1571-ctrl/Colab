"""collab-tools schema: Task, TaskComment, WhiteboardSnapshot, WhiteboardOp, WhiteboardExport.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-11

Tables added to collab schema:
- collab.task
- collab.task_comment
- collab.whiteboard_snapshot
- collab.whiteboard_op
- collab.whiteboard_export
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # New ENUMs
    # -----------------------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE collab.task_status AS ENUM (
                'todo', 'in_progress', 'done', 'blocked'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE collab.whiteboard_export_status AS ENUM (
                'pending', 'generating', 'ready', 'failed'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    # -----------------------------------------------------------------------
    # collab.task
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE collab.task (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collab_id            UUID NOT NULL
                                   REFERENCES collab.collaboration(id) ON DELETE CASCADE,
            title                VARCHAR(200) NOT NULL
                                   CHECK (char_length(title) BETWEEN 1 AND 200),
            description          TEXT
                                   CHECK (char_length(description) <= 2000),
            assignee_profile_id  UUID,
            due_date             DATE,
            status               collab.task_status NOT NULL DEFAULT 'todo',
            order_key            VARCHAR(255) NOT NULL,
            created_by           UUID NOT NULL,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            closed_at            TIMESTAMPTZ,
            deleted_at           TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE INDEX idx_task_collab_order
            ON collab.task (collab_id, order_key)
            WHERE deleted_at IS NULL
    """)
    op.execute("""
        CREATE INDEX idx_task_collab_due
            ON collab.task (collab_id, due_date)
            WHERE deleted_at IS NULL
    """)
    op.execute("""
        CREATE INDEX idx_task_collab_status
            ON collab.task (collab_id, status)
            WHERE deleted_at IS NULL
    """)
    op.execute("""
        CREATE INDEX idx_task_assignee
            ON collab.task (assignee_profile_id)
            WHERE assignee_profile_id IS NOT NULL AND deleted_at IS NULL
    """)

    # Auto-update updated_at on row change
    op.execute("""
        CREATE OR REPLACE FUNCTION collab.set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_task_updated_at
        BEFORE UPDATE ON collab.task
        FOR EACH ROW EXECUTE FUNCTION collab.set_updated_at();
    """)

    # -----------------------------------------------------------------------
    # collab.task_comment
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE collab.task_comment (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            task_id           UUID NOT NULL
                                REFERENCES collab.task(id) ON DELETE CASCADE,
            author_profile_id UUID NOT NULL,
            body              VARCHAR(500) NOT NULL
                                CHECK (char_length(body) BETWEEN 1 AND 500),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at        TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE INDEX idx_task_comment_task
            ON collab.task_comment (task_id, created_at)
            WHERE deleted_at IS NULL
    """)

    # -----------------------------------------------------------------------
    # collab.whiteboard_snapshot
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE collab.whiteboard_snapshot (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collab_id   UUID NOT NULL
                          REFERENCES collab.collaboration(id) ON DELETE CASCADE,
            s3_key      TEXT NOT NULL,
            version     BIGINT NOT NULL DEFAULT 0,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE INDEX idx_whiteboard_snapshot_collab_version
            ON collab.whiteboard_snapshot (collab_id, version DESC)
    """)

    # -----------------------------------------------------------------------
    # collab.whiteboard_op  (Y.js binary op log)
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE collab.whiteboard_op (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collab_id        UUID NOT NULL
                               REFERENCES collab.collaboration(id) ON DELETE CASCADE,
            lamport          BIGINT NOT NULL,
            actor_profile_id UUID NOT NULL,
            op_data          BYTEA NOT NULL,
            applied_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE INDEX idx_whiteboard_op_collab_lamport
            ON collab.whiteboard_op (collab_id, lamport)
    """)

    # -----------------------------------------------------------------------
    # collab.whiteboard_export
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE collab.whiteboard_export (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collab_id    UUID NOT NULL
                           REFERENCES collab.collaboration(id) ON DELETE CASCADE,
            requested_by UUID NOT NULL,
            format       VARCHAR(10) NOT NULL CHECK (format IN ('png', 'pdf')),
            resolution   VARCHAR(10) NOT NULL CHECK (resolution IN ('basic', 'hi')),
            status       collab.whiteboard_export_status NOT NULL DEFAULT 'pending',
            s3_key       TEXT,
            error_detail TEXT,
            requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            expires_at   TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE INDEX idx_whiteboard_export_collab
            ON collab.whiteboard_export (collab_id, requested_at DESC)
    """)
    op.execute("""
        CREATE INDEX idx_whiteboard_export_requested_by
            ON collab.whiteboard_export (requested_by)
    """)
    op.execute("""
        CREATE INDEX idx_whiteboard_export_status
            ON collab.whiteboard_export (status)
            WHERE status IN ('pending', 'generating')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS collab.whiteboard_export CASCADE")
    op.execute("DROP TABLE IF EXISTS collab.whiteboard_op CASCADE")
    op.execute("DROP TABLE IF EXISTS collab.whiteboard_snapshot CASCADE")
    op.execute("DROP TABLE IF EXISTS collab.task_comment CASCADE")
    op.execute("DROP TABLE IF EXISTS collab.task CASCADE")
    op.execute("DROP TRIGGER IF EXISTS trg_task_updated_at ON collab.task")
    op.execute("DROP FUNCTION IF EXISTS collab.set_updated_at")
    op.execute("DROP TYPE IF EXISTS collab.whiteboard_export_status CASCADE")
    op.execute("DROP TYPE IF EXISTS collab.task_status CASCADE")
