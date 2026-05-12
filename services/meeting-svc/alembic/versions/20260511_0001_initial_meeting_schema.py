"""Initial meeting schema.

Revision ID: 0001
Revises:
Create Date: 2026-05-11

Tables (all in schema 'meeting'):
- meeting.meeting
- meeting.meeting_artifact
- meeting.meeting_bot_consent

Indexes:
- idx_meeting_collab   (collab_id)
- idx_meeting_scheduled (scheduled_at WHERE status='scheduled')
- idx_artifact_meeting  (meeting_id)
- idx_consent_meeting   (meeting_id)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # Schema
    # -----------------------------------------------------------------------
    op.execute("CREATE SCHEMA IF NOT EXISTS meeting")

    # -----------------------------------------------------------------------
    # Enums
    # -----------------------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE meeting.meeting_status AS ENUM (
                'scheduled', 'started', 'ended', 'cancelled'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE meeting.bot_status AS ENUM (
                'none', 'requested', 'joining', 'joined', 'left', 'failed'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE meeting.artifact_kind AS ENUM (
                'transcript', 'recording', 'summary'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    # -----------------------------------------------------------------------
    # meeting.meeting
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE meeting.meeting (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collab_id           UUID NOT NULL,
            organizer_profile_id UUID NOT NULL,
            scheduled_at        TIMESTAMPTZ NOT NULL,
            duration_min        SMALLINT NOT NULL DEFAULT 60
                                    CHECK (duration_min BETWEEN 15 AND 480),
            join_url            TEXT NOT NULL,
            ics_s3_key          TEXT,
            gcal_event_id       TEXT,
            gcal_request_id     UUID NOT NULL UNIQUE,
            status              meeting.meeting_status NOT NULL DEFAULT 'scheduled',
            bot_enabled         BOOLEAN NOT NULL DEFAULT FALSE,
            bot_status          meeting.bot_status NOT NULL DEFAULT 'none',
            recall_bot_id       TEXT,
            cancelled_at        TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX idx_meeting_collab ON meeting.meeting(collab_id)
    """)

    op.execute("""
        CREATE INDEX idx_meeting_scheduled
            ON meeting.meeting(scheduled_at)
            WHERE status = 'scheduled'
    """)

    # Auto-update updated_at trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION meeting.set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_meeting_updated_at
            BEFORE UPDATE ON meeting.meeting
            FOR EACH ROW EXECUTE FUNCTION meeting.set_updated_at()
    """)

    # -----------------------------------------------------------------------
    # meeting.meeting_artifact
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE meeting.meeting_artifact (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            meeting_id  UUID NOT NULL
                            REFERENCES meeting.meeting(id) ON DELETE CASCADE,
            kind        meeting.artifact_kind NOT NULL,
            s3_key      TEXT NOT NULL,
            size_bytes  BIGINT,
            ready_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX idx_artifact_meeting ON meeting.meeting_artifact(meeting_id)
    """)

    # -----------------------------------------------------------------------
    # meeting.meeting_bot_consent
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE meeting.meeting_bot_consent (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            meeting_id   UUID NOT NULL
                             REFERENCES meeting.meeting(id) ON DELETE CASCADE,
            profile_id   UUID NOT NULL,
            consented_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            revoked_at   TIMESTAMPTZ,
            CONSTRAINT uq_consent_meeting_profile UNIQUE (meeting_id, profile_id)
        )
    """)

    op.execute("""
        CREATE INDEX idx_consent_meeting ON meeting.meeting_bot_consent(meeting_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS meeting.meeting_bot_consent CASCADE")
    op.execute("DROP TABLE IF EXISTS meeting.meeting_artifact CASCADE")
    op.execute("DROP TRIGGER IF EXISTS trg_meeting_updated_at ON meeting.meeting")
    op.execute("DROP FUNCTION IF EXISTS meeting.set_updated_at()")
    op.execute("DROP TABLE IF EXISTS meeting.meeting CASCADE")
    op.execute("DROP TYPE IF EXISTS meeting.artifact_kind CASCADE")
    op.execute("DROP TYPE IF EXISTS meeting.bot_status CASCADE")
    op.execute("DROP TYPE IF EXISTS meeting.meeting_status CASCADE")
    op.execute("DROP SCHEMA IF EXISTS meeting CASCADE")
