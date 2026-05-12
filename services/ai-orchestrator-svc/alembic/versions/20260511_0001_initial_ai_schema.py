"""Initial ai schema — mockup_consent, mockup_asset, ai_interaction, mockup_screenshot_audit.

Revision ID: 0001
Revises:
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # Schema
    # -----------------------------------------------------------------------
    op.execute("CREATE SCHEMA IF NOT EXISTS ai")

    # -----------------------------------------------------------------------
    # Enums
    # -----------------------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE ai.mockup_consent_status AS ENUM (
                'pending_b', 'approved', 'rejected', 'expired', 'generated'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE ai.generation_kind AS ENUM ('image', 'audio', 'both');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE ai.mockup_asset_kind AS ENUM ('image', 'audio');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE ai.mockup_moderation_status AS ENUM ('passed', 'blocked');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE ai.ai_command AS ENUM (
                'mockup_image', 'mockup_audio', 'summarize_chat', 'brainstorm', 'palette'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE ai.ai_interaction_status AS ENUM (
                'queued', 'processing', 'completed', 'failed',
                'moderation_blocked', 'refunded', 'rejected_insufficient_credits'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE ai.screenshot_platform AS ENUM ('ios', 'android');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    # -----------------------------------------------------------------------
    # mockup_consent
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE ai.mockup_consent (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collab_id            UUID NOT NULL,
            requested_by         UUID NOT NULL,
            party_a_consented_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            party_b_consented_at TIMESTAMPTZ,
            lifespan_days        SMALLINT NOT NULL DEFAULT 1
                                     CHECK (lifespan_days IN (1, 14)),
            brief                VARCHAR(500) NOT NULL DEFAULT '',
            status               ai.mockup_consent_status NOT NULL DEFAULT 'pending_b',
            generation_kind      ai.generation_kind NOT NULL DEFAULT 'image',
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_consent_at   TIMESTAMPTZ NOT NULL
        )
    """)

    # Partial unique index: only one active consent per collab
    op.execute("""
        CREATE UNIQUE INDEX idx_mockup_consent_collab_active
            ON ai.mockup_consent (collab_id)
            WHERE status IN ('pending_b', 'approved')
    """)

    op.execute("""
        CREATE INDEX idx_mockup_consent_expires
            ON ai.mockup_consent (expires_consent_at)
            WHERE status = 'pending_b'
    """)

    # -----------------------------------------------------------------------
    # mockup_asset
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE ai.mockup_asset (
            id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            mockup_consent_id      UUID REFERENCES ai.mockup_consent(id),
            replicate_prediction_id VARCHAR(64) NOT NULL UNIQUE,
            kind                   ai.mockup_asset_kind NOT NULL,
            s3_key                 TEXT NOT NULL DEFAULT '',
            watermark_meta         JSONB NOT NULL DEFAULT '{}',
            moderation_score       NUMERIC(4, 3),
            moderation_status      ai.mockup_moderation_status,
            generated_at           TIMESTAMPTZ,
            expires_at             TIMESTAMPTZ,
            active                 BOOLEAN NOT NULL DEFAULT true,
            file_size_bytes        BIGINT,
            duration_ms            INTEGER,
            width                  INTEGER,
            height                 INTEGER
        )
    """)

    op.execute("""
        CREATE INDEX idx_mockup_asset_consent_id ON ai.mockup_asset (mockup_consent_id)
    """)

    op.execute("""
        CREATE INDEX idx_mockup_asset_expires_active
            ON ai.mockup_asset (expires_at)
            WHERE active = true
    """)

    op.execute("""
        CREATE INDEX idx_mockup_asset_replicate_id
            ON ai.mockup_asset (replicate_prediction_id)
    """)

    # -----------------------------------------------------------------------
    # ai_interaction
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE ai.ai_interaction (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id                 UUID NOT NULL,
            collab_id               UUID,
            room_id                 UUID,
            command                 ai.ai_command NOT NULL,
            args_json               JSONB NOT NULL DEFAULT '{}',
            input_tokens            INTEGER,
            output_tokens           INTEGER,
            cost_credits            INTEGER NOT NULL DEFAULT 0,
            replicate_prediction_id VARCHAR(64),
            mockup_asset_id         UUID REFERENCES ai.mockup_asset(id),
            billing_reservation_id  UUID,
            status                  ai.ai_interaction_status NOT NULL DEFAULT 'queued',
            failure_reason          TEXT,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at            TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE INDEX idx_ai_interaction_user_created
            ON ai.ai_interaction (user_id, created_at DESC)
    """)

    op.execute("""
        CREATE INDEX idx_ai_interaction_replicate_id
            ON ai.ai_interaction (replicate_prediction_id)
            WHERE replicate_prediction_id IS NOT NULL
    """)

    # -----------------------------------------------------------------------
    # mockup_screenshot_audit
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE ai.mockup_screenshot_audit (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            mockup_asset_id  UUID NOT NULL REFERENCES ai.mockup_asset(id),
            user_id          UUID NOT NULL,
            platform         ai.screenshot_platform NOT NULL,
            detected_at      TIMESTAMPTZ NOT NULL,
            raw_event        JSONB NOT NULL DEFAULT '{}'
        )
    """)

    op.execute("""
        CREATE INDEX idx_screenshot_audit_asset_id
            ON ai.mockup_screenshot_audit (mockup_asset_id)
    """)

    op.execute("""
        CREATE INDEX idx_screenshot_audit_user_id
            ON ai.mockup_screenshot_audit (user_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ai.mockup_screenshot_audit CASCADE")
    op.execute("DROP TABLE IF EXISTS ai.ai_interaction CASCADE")
    op.execute("DROP TABLE IF EXISTS ai.mockup_asset CASCADE")
    op.execute("DROP TABLE IF EXISTS ai.mockup_consent CASCADE")

    op.execute("DROP TYPE IF EXISTS ai.screenshot_platform")
    op.execute("DROP TYPE IF EXISTS ai.ai_interaction_status")
    op.execute("DROP TYPE IF EXISTS ai.ai_command")
    op.execute("DROP TYPE IF EXISTS ai.mockup_moderation_status")
    op.execute("DROP TYPE IF EXISTS ai.mockup_asset_kind")
    op.execute("DROP TYPE IF EXISTS ai.generation_kind")
    op.execute("DROP TYPE IF EXISTS ai.mockup_consent_status")

    op.execute("DROP SCHEMA IF EXISTS ai CASCADE")
