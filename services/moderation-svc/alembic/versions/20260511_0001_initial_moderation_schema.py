"""Initial moderation schema.

Revision ID: 0001
Revises:
Create Date: 2026-05-11

Tables created:
- moderation.moderation_cases
- moderation.moderation_actions  (append-only; trigger blocks UPDATE/DELETE)
- moderation.reports
- moderation.report_throttle
- moderation.dmca_notices
- moderation.counter_notices
- moderation.banned_hash_registry
- moderation.banned_audio_fingerprints
- moderation.banned_text_embeddings (pgvector vector column)
- moderation.mod_scan_log
- moderation.action_propagation_log
- moderation.mod_config
- moderation.event_outbox (shared pattern from colab_common.events)

DB trigger: blocks UPDATE + DELETE on moderation_actions (append-only audit).
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
    # ---------------------------------------------------------------------------
    # Schema
    # ---------------------------------------------------------------------------
    op.execute("CREATE SCHEMA IF NOT EXISTS moderation")

    # pgvector extension (shared with matching-svc; idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ---------------------------------------------------------------------------
    # Enums
    # ---------------------------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE moderation.case_kind AS ENUM ('auto', 'report', 'dmca');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE moderation.subject_type AS ENUM (
                'msg', 'profile_field', 'portfolio_item', 'invite_synopsis', 'mockup', 'user'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE moderation.case_status AS ENUM (
                'open', 'in_review', 'actioned', 'dismissed', 'escalated'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE moderation.priority_tier AS ENUM (
                'tier_0_allow', 'tier_1_24h', 'tier_2_6h', 'tier_3_1h'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE moderation.action_type AS ENUM (
                'warn', 'hide', 'restore', 'temp_mute_1h', 'temp_mute_24h', 'temp_mute_7d',
                'permanent_ban', 'delete_account', 'dismiss', 'escalate_to_legal'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE moderation.propagation_status AS ENUM (
                'pending', 'partial', 'complete', 'failed'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE moderation.dmca_state AS ENUM (
                'received', 'hidden', 'counter_pending', 'restored', 'permanent', 'rejected_defective'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE moderation.counter_notice_state AS ENUM (
                'received', 'awaiting_window', 'restored', 'permanent_taken_down'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    # ---------------------------------------------------------------------------
    # moderation_cases
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE moderation.moderation_cases (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            kind                  moderation.case_kind NOT NULL,
            subject_type          moderation.subject_type NOT NULL,
            subject_id            UUID NOT NULL,
            subject_owner_user_id UUID NOT NULL,
            reporter_user_id      UUID,
            score                 NUMERIC(3,2),
            scores_breakdown      JSONB NOT NULL DEFAULT '{}',
            forced_human          BOOLEAN NOT NULL DEFAULT FALSE,
            forced_reason         VARCHAR(200),
            status                moderation.case_status NOT NULL DEFAULT 'open',
            priority_tier         moderation.priority_tier NOT NULL DEFAULT 'tier_1_24h',
            sla_due_at            TIMESTAMPTZ,
            sla_breached_at       TIMESTAMPTZ,
            opened_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
            claimed_by            UUID,
            claimed_at            TIMESTAMPTZ,
            actioned_at           TIMESTAMPTZ,
            actioned_by           UUID,
            action_type           moderation.action_type,
            second_reviewer_id    UUID,
            idempotency_key       VARCHAR(512) UNIQUE,
            parent_case_id        UUID REFERENCES moderation.moderation_cases(id),
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Indexes for queue + lookup performance
    op.execute("""
        CREATE INDEX ix_mod_case_queue ON moderation.moderation_cases
            (status, priority_tier DESC, sla_due_at ASC)
    """)
    op.execute("""
        CREATE INDEX ix_mod_case_subject ON moderation.moderation_cases
            (subject_type, subject_id)
    """)
    op.execute("""
        CREATE INDEX ix_mod_case_owner ON moderation.moderation_cases
            (subject_owner_user_id, opened_at DESC)
    """)

    # ---------------------------------------------------------------------------
    # moderation_actions — APPEND-ONLY
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE moderation.moderation_actions (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id             UUID NOT NULL REFERENCES moderation.moderation_cases(id),
            action_type         moderation.action_type NOT NULL,
            reviewer_id         UUID NOT NULL,
            reason              TEXT NOT NULL,
            evidence_refs       JSONB NOT NULL DEFAULT '[]',
            target_user_id      UUID NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            propagation_status  moderation.propagation_status NOT NULL DEFAULT 'pending',
            propagation_events  JSONB NOT NULL DEFAULT '{}'
        )
    """)
    op.execute("""
        CREATE INDEX ix_mod_action_case ON moderation.moderation_actions
            (case_id, created_at)
    """)
    op.execute("""
        CREATE INDEX ix_mod_action_target ON moderation.moderation_actions
            (target_user_id, created_at)
    """)

    # Append-only trigger — blocks UPDATE and DELETE
    op.execute("""
        CREATE OR REPLACE FUNCTION moderation.no_modify_actions()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'moderation_actions is append-only: UPDATE and DELETE are not permitted. '
                            'All corrections must be made via new rows.';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_moderation_actions_no_modify
        BEFORE UPDATE OR DELETE ON moderation.moderation_actions
        FOR EACH ROW EXECUTE FUNCTION moderation.no_modify_actions()
    """)

    # ---------------------------------------------------------------------------
    # reports
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE moderation.reports (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            reporter_user_id  UUID NOT NULL,
            subject_type      moderation.subject_type NOT NULL,
            subject_id        UUID NOT NULL,
            description       VARCHAR(1000) NOT NULL,
            screenshot_s3_key TEXT,
            case_id           UUID REFERENCES moderation.moderation_cases(id),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            reporter_ip       INET,
            device_id         VARCHAR(255)
        )
    """)
    op.execute("""
        CREATE INDEX ix_report_reporter ON moderation.reports
            (reporter_user_id, created_at)
    """)
    op.execute("""
        CREATE INDEX ix_report_subject ON moderation.reports
            (subject_type, subject_id)
    """)

    # ---------------------------------------------------------------------------
    # report_throttle
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE moderation.report_throttle (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            reporter_user_id  UUID NOT NULL,
            day               TIMESTAMPTZ NOT NULL,
            count             INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT uq_report_throttle_user_day UNIQUE (reporter_user_id, day)
        )
    """)

    # ---------------------------------------------------------------------------
    # dmca_notices
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE moderation.dmca_notices (
            id                                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            claimant_name                         VARCHAR(200) NOT NULL,
            claimant_address                      TEXT NOT NULL,
            claimant_phone                        VARCHAR(40) NOT NULL,
            claimant_email                        VARCHAR(320) NOT NULL,
            is_authorized_agent                   BOOLEAN NOT NULL,
            sworn_statement_text                  TEXT NOT NULL,
            signature_full_name                   VARCHAR(200) NOT NULL,
            hash_of_signature                     BYTEA NOT NULL,
            copyrighted_work_description          TEXT NOT NULL,
            copyrighted_work_url_or_registration  TEXT,
            target_subject_type                   moderation.subject_type NOT NULL,
            target_subject_id                     UUID NOT NULL,
            target_url_on_colab                   TEXT NOT NULL,
            target_user_id                        UUID NOT NULL,
            claimant_ip                           INET,
            received_at                           TIMESTAMPTZ NOT NULL DEFAULT now(),
            hide_at                               TIMESTAMPTZ,
            hidden_at                             TIMESTAMPTZ,
            state                                 moderation.dmca_state NOT NULL DEFAULT 'received',
            rejection_reason                      TEXT,
            case_id                               UUID REFERENCES moderation.moderation_cases(id)
        )
    """)
    op.execute("""
        CREATE INDEX ix_dmca_state ON moderation.dmca_notices (state, hide_at)
    """)

    # ---------------------------------------------------------------------------
    # counter_notices
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE moderation.counter_notices (
            id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            dmca_id                      UUID NOT NULL UNIQUE REFERENCES moderation.dmca_notices(id),
            counter_claimant_user_id     UUID NOT NULL,
            counter_claimant_legal_name  VARCHAR(200) NOT NULL,
            counter_claimant_address     TEXT NOT NULL,
            counter_claimant_phone       VARCHAR(40) NOT NULL,
            counter_statement_text       TEXT NOT NULL,
            consent_to_jurisdiction      BOOLEAN NOT NULL,
            consent_to_service_of_process BOOLEAN NOT NULL,
            signature_full_name          VARCHAR(200) NOT NULL,
            hash_of_signature            BYTEA NOT NULL,
            received_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
            statutory_window_end         TIMESTAMPTZ,
            forwarded_to_claimant_at     TIMESTAMPTZ,
            suit_filed_notice_received_at TIMESTAMPTZ,
            restored_at                  TIMESTAMPTZ,
            state                        moderation.counter_notice_state NOT NULL DEFAULT 'received'
        )
    """)
    op.execute("""
        CREATE INDEX ix_counter_window ON moderation.counter_notices
            (state, statutory_window_end)
    """)

    # ---------------------------------------------------------------------------
    # banned_hash_registry (pHash image dup)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE moderation.banned_hash_registry (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            hash_phash BYTEA NOT NULL UNIQUE,
            source     VARCHAR(200) NOT NULL,
            severity   VARCHAR(50) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            notes      TEXT
        )
    """)

    # ---------------------------------------------------------------------------
    # banned_audio_fingerprints (Chromaprint)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE moderation.banned_audio_fingerprints (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            fingerprint INTEGER[] NOT NULL,
            source      VARCHAR(200) NOT NULL,
            severity    VARCHAR(50) NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # ---------------------------------------------------------------------------
    # banned_text_embeddings (pgvector semantic dup)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE moderation.banned_text_embeddings (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            embedding      vector(3072) NOT NULL,
            source         VARCHAR(200) NOT NULL,
            severity       VARCHAR(50) NOT NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # IVFFlat index for approximate cosine similarity
    op.execute("""
        CREATE INDEX ix_banned_text_emb_ivf ON moderation.banned_text_embeddings
            USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
    """)

    # ---------------------------------------------------------------------------
    # mod_scan_log
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE moderation.mod_scan_log (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            subject_type     moderation.subject_type NOT NULL,
            subject_id       UUID NOT NULL,
            idempotency_key  VARCHAR(512),
            tool             VARCHAR(100) NOT NULL,
            score            NUMERIC(5,4),
            raw_response     JSONB NOT NULL DEFAULT '{}',
            scanned_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX ix_scan_log_subject ON moderation.mod_scan_log
            (subject_type, subject_id, scanned_at)
    """)

    # ---------------------------------------------------------------------------
    # action_propagation_log — append-only audit
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE moderation.action_propagation_log (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            action_id       UUID NOT NULL REFERENCES moderation.moderation_actions(id),
            target_event    VARCHAR(200) NOT NULL,
            target_service  VARCHAR(100) NOT NULL,
            status          VARCHAR(50) NOT NULL,
            payload         JSONB NOT NULL DEFAULT '{}',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX ix_prop_log_action ON moderation.action_propagation_log
            (action_id, created_at)
    """)

    # Append-only trigger for propagation log as well
    op.execute("""
        CREATE OR REPLACE FUNCTION moderation.no_modify_prop_log()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'action_propagation_log is append-only.';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_prop_log_no_modify
        BEFORE UPDATE OR DELETE ON moderation.action_propagation_log
        FOR EACH ROW EXECUTE FUNCTION moderation.no_modify_prop_log()
    """)

    # ---------------------------------------------------------------------------
    # mod_config — admin-tunable thresholds
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE moderation.mod_config (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            key         VARCHAR(255) NOT NULL,
            value       TEXT NOT NULL,
            description TEXT,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_by  UUID,
            CONSTRAINT uq_mod_config_key UNIQUE (key)
        )
    """)

    # Seed default configuration values
    op.execute("""
        INSERT INTO moderation.mod_config (key, value, description) VALUES
            ('tier1_threshold', '0.4', 'Score threshold for tier_1 (soft-warn + 24h SLA)'),
            ('tier2_threshold', '0.7', 'Score threshold for tier_2 (hide + 6h SLA)'),
            ('tier3_threshold', '0.9', 'Score threshold for tier_3 (auto-hide + mute + 1h SLA)'),
            ('dup_bump', '0.3', 'Score bump when any dup signal fires'),
            ('phash_hamming_threshold', '6', 'Hamming distance threshold for pHash dup (max 64 bits)'),
            ('chromaprint_sim_threshold', '0.85', 'Chromaprint cosine similarity threshold for audio dup'),
            ('semdup_cosine_threshold', '0.95', 'pgvector cosine threshold for semantic dup'),
            ('reports_per_user_per_day', '20', 'Daily report limit per user (anti-bombing)'),
            ('dmca_per_ip_per_day', '5', 'DMCA notice rate limit per source IP'),
            ('dmca_per_email_per_day', '10', 'DMCA notice rate limit per claimant email'),
            ('dmca_statutory_window_days', '14', 'Counter-notice statutory window in calendar days'),
            ('weight_sexual_minors', '1.5', 'Category weight multiplier for sexual/minors'),
            ('weight_harassment_threatening', '1.3', 'Category weight multiplier for harassment/threatening'),
            ('weight_hate_threatening', '1.3', 'Category weight multiplier for hate/threatening'),
            ('weight_violence_graphic', '1.2', 'Category weight multiplier for violence/graphic'),
            ('weight_selfharm_intent', '1.2', 'Category weight multiplier for self-harm/intent'),
            ('weight_rek_explicit', '1.2', 'Rekognition Explicit category weight'),
            ('weight_rek_hate_symbols', '1.3', 'Rekognition Hate Symbols category weight')
        ON CONFLICT (key) DO NOTHING
    """)

    # ---------------------------------------------------------------------------
    # event_outbox (colab_common pattern)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS moderation.event_outbox (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_name     VARCHAR(255) NOT NULL,
            payload        TEXT NOT NULL,
            dedupe_key     VARCHAR(512) UNIQUE,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            published_at   TIMESTAMPTZ,
            failed_attempts VARCHAR(10) DEFAULT '0'
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_event_outbox_unpublished ON moderation.event_outbox
            (created_at) WHERE published_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS moderation CASCADE")
