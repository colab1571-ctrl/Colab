"""Initial collab schema.

Revision ID: 0001
Revises:
Create Date: 2026-05-11

Tables:
- collab.collaboration (with search_vector tsvector + GIN index)
- collab.collab_status_event
- collab.collab_feedback (thumbs up/down + tag chips; idempotent upsert key)
- collab.collab_export
- collab.collab_file_name (FTS denormalization)
- collab.collab_participant_name_cache (FTS denormalization)

Triggers:
- collab.refresh_search_vector(collab_id) — recomputes tsvector
- trg_collaboration_search_vector — fires on INSERT/UPDATE of title/description
- trg_collab_file_name_search_vector — fires on INSERT into collab_file_name
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
    op.execute("CREATE SCHEMA IF NOT EXISTS collab")

    # -----------------------------------------------------------------------
    # Enums
    # -----------------------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE collab.collab_status AS ENUM (
                'still_deciding', 'in_progress', 'completed', 'didnt_work_out'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE collab.feedback_rating AS ENUM ('up', 'down');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE collab.feedback_target AS ENUM ('project', 'partner');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE collab.feedback_tag AS ENUM (
                'communicative',
                'responsive',
                'professional',
                'creative',
                'reliable',
                'flexible',
                'ghosted',
                'slow_to_respond',
                'missed_deadlines',
                'scope_creep',
                'great_outcome',
                'met_goals',
                'learned_a_lot',
                'good_creative_fit',
                'incomplete',
                'unclear_direction',
                'changed_scope',
                'technical_issues'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE collab.export_status AS ENUM (
                'pending', 'generating', 'ready', 'failed'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    # -----------------------------------------------------------------------
    # collab.collaboration
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE collab.collaboration (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            profile_id_a        UUID NOT NULL,
            profile_id_b        UUID NOT NULL,
            least_participant   UUID NOT NULL
                                  GENERATED ALWAYS AS (LEAST(profile_id_a, profile_id_b)) STORED,
            greatest_participant UUID NOT NULL
                                  GENERATED ALWAYS AS (GREATEST(profile_id_a, profile_id_b)) STORED,
            title               TEXT,
            description         TEXT,
            status              collab.collab_status NOT NULL DEFAULT 'still_deciding',
            is_read_only        BOOLEAN NOT NULL DEFAULT FALSE,
            last_activity_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            nudge_sent_at       TIMESTAMPTZ,
            archive_at          TIMESTAMPTZ,
            archived_at         TIMESTAMPTZ,
            completed_at        TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            search_vector       TSVECTOR
        )
    """)

    op.execute("""
        CREATE UNIQUE INDEX collaboration_participants_unique
            ON collab.collaboration (least_participant, greatest_participant)
    """)
    op.execute("""
        CREATE INDEX idx_collaboration_search_vector
            ON collab.collaboration USING GIN (search_vector)
    """)
    op.execute("CREATE INDEX idx_collaboration_profile_a ON collab.collaboration (profile_id_a)")
    op.execute("CREATE INDEX idx_collaboration_profile_b ON collab.collaboration (profile_id_b)")
    op.execute("CREATE INDEX idx_collaboration_status ON collab.collaboration (status)")
    op.execute("CREATE INDEX idx_collaboration_last_activity ON collab.collaboration (last_activity_at)")
    op.execute("""
        CREATE INDEX idx_collaboration_archive_at
            ON collab.collaboration (archive_at)
            WHERE archive_at IS NOT NULL
    """)

    # -----------------------------------------------------------------------
    # collab.collab_participant_name_cache (needed by search vector trigger)
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE collab.collab_participant_name_cache (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collab_id    UUID NOT NULL REFERENCES collab.collaboration(id) ON DELETE CASCADE,
            profile_id   UUID NOT NULL,
            display_name TEXT NOT NULL,
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT collab_name_cache_unique UNIQUE (collab_id, profile_id)
        )
    """)
    op.execute("CREATE INDEX idx_collab_name_cache_collab ON collab.collab_participant_name_cache (collab_id)")

    # -----------------------------------------------------------------------
    # collab.collab_file_name (FTS denorm)
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE collab.collab_file_name (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collab_id  UUID NOT NULL REFERENCES collab.collaboration(id) ON DELETE CASCADE,
            s3_key     TEXT NOT NULL,
            file_name  TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_collab_file_name_collab ON collab.collab_file_name (collab_id)")

    # -----------------------------------------------------------------------
    # Search vector refresh function + triggers
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION collab.refresh_search_vector(p_collab_id UUID)
        RETURNS VOID AS $$
        DECLARE
            v_title       TEXT;
            v_description TEXT;
            v_names       TEXT;
            v_file_names  TEXT;
        BEGIN
            SELECT c.title, c.description
            INTO v_title, v_description
            FROM collab.collaboration c
            WHERE c.id = p_collab_id;

            SELECT string_agg(display_name, ' ')
            INTO v_names
            FROM collab.collab_participant_name_cache
            WHERE collab_id = p_collab_id;

            SELECT string_agg(file_name, ' ')
            INTO v_file_names
            FROM collab.collab_file_name
            WHERE collab_id = p_collab_id;

            UPDATE collab.collaboration
            SET search_vector =
                setweight(to_tsvector('english', coalesce(v_title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(v_description, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(v_names, '')), 'C') ||
                setweight(to_tsvector('english', coalesce(v_file_names, '')), 'D')
            WHERE id = p_collab_id;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION collab.trg_collaboration_search_vector()
        RETURNS TRIGGER AS $$
        BEGIN
            PERFORM collab.refresh_search_vector(NEW.id);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_collaboration_search_vector
        AFTER INSERT OR UPDATE OF title, description
        ON collab.collaboration
        FOR EACH ROW EXECUTE FUNCTION collab.trg_collaboration_search_vector();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION collab.trg_collab_file_name_search_vector()
        RETURNS TRIGGER AS $$
        BEGIN
            PERFORM collab.refresh_search_vector(NEW.collab_id);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_collab_file_name_search_vector
        AFTER INSERT ON collab.collab_file_name
        FOR EACH ROW EXECUTE FUNCTION collab.trg_collab_file_name_search_vector();
    """)

    # -----------------------------------------------------------------------
    # collab.collab_status_event
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE collab.collab_status_event (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collab_id        UUID NOT NULL REFERENCES collab.collaboration(id) ON DELETE CASCADE,
            actor_profile_id UUID NOT NULL,
            prev_status      TEXT NOT NULL,
            new_status       TEXT NOT NULL,
            note             TEXT CHECK (char_length(note) <= 500),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX idx_collab_status_event_collab
            ON collab.collab_status_event (collab_id, created_at)
    """)

    # -----------------------------------------------------------------------
    # collab.collab_feedback
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE collab.collab_feedback (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collab_id       UUID NOT NULL REFERENCES collab.collaboration(id) ON DELETE CASCADE,
            from_profile_id UUID NOT NULL,
            to_profile_id   UUID,
            target          collab.feedback_target NOT NULL,
            rating          collab.feedback_rating NOT NULL,
            tags            TEXT[] NOT NULL DEFAULT '{}',
            comment         TEXT CHECK (char_length(comment) <= 500),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT collab_feedback_unique UNIQUE (collab_id, from_profile_id, target)
        )
    """)
    op.execute("CREATE INDEX idx_collab_feedback_collab ON collab.collab_feedback (collab_id)")
    op.execute("CREATE INDEX idx_collab_feedback_from ON collab.collab_feedback (from_profile_id)")
    op.execute("""
        CREATE INDEX idx_collab_feedback_to
            ON collab.collab_feedback (to_profile_id)
            WHERE to_profile_id IS NOT NULL
    """)

    # -----------------------------------------------------------------------
    # collab.collab_export
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE collab.collab_export (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collab_id    UUID NOT NULL REFERENCES collab.collaboration(id) ON DELETE CASCADE,
            requested_by UUID NOT NULL,
            status       collab.export_status NOT NULL DEFAULT 'pending',
            pdf_s3_key   TEXT,
            zip_s3_key   TEXT,
            error_detail TEXT,
            requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at   TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            expires_at   TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX idx_collab_export_collab ON collab.collab_export (collab_id)")
    op.execute("CREATE INDEX idx_collab_export_requested_by ON collab.collab_export (requested_by)")
    op.execute("""
        CREATE INDEX idx_collab_export_status
            ON collab.collab_export (status)
            WHERE status IN ('pending', 'generating')
    """)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS collab CASCADE")
