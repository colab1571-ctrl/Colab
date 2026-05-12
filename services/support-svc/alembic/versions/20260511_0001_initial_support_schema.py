"""Initial support schema.

Revision ID: 0001
Revises:
Create Date: 2026-05-11

Tables created:
- support.support_ticket
- support.support_ticket_event
- support.support_csat
- support.kb_article          (pgvector embedding vector(3072), ivfflat index)
- support.chatbot_session
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
    # -------------------------------------------------------------------------
    # Schema + extensions
    # -------------------------------------------------------------------------
    op.execute("CREATE SCHEMA IF NOT EXISTS support")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # -------------------------------------------------------------------------
    # support.support_ticket
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE support.support_ticket (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id                 UUID NOT NULL,
            category                TEXT NOT NULL
                                        CHECK (category IN (
                                            'harassment_threats','ip_dmca',
                                            'payment','technical','other')),
            subject                 TEXT NOT NULL CHECK (char_length(subject) BETWEEN 1 AND 255),
            body                    TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 8000),
            status                  TEXT NOT NULL DEFAULT 'open'
                                        CHECK (status IN ('open','in_progress','pending_user',
                                                          'resolved','closed')),
            priority                TEXT NOT NULL DEFAULT 'normal'
                                        CHECK (priority IN ('normal','high','critical')),
            tier_at_creation        TEXT NOT NULL DEFAULT 'free'
                                        CHECK (tier_at_creation IN ('free','premium','premium_pro')),
            assigned_to             UUID,
            sla_ack_due             TIMESTAMPTZ NOT NULL,
            sla_resolve_due         TIMESTAMPTZ NOT NULL,
            sla_paused_seconds      INTEGER NOT NULL DEFAULT 0,
            sla_ack_breached_at     TIMESTAMPTZ,
            sla_resolve_breached_at TIMESTAMPTZ,
            sla_paused_at           TIMESTAMPTZ,
            first_response_at       TIMESTAMPTZ,
            resolved_at             TIMESTAMPTZ,
            moderation_case_id      UUID,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute("CREATE INDEX idx_st_user_id ON support.support_ticket(user_id)")
    op.execute("CREATE INDEX idx_st_status ON support.support_ticket(status)")
    op.execute(
        """
        CREATE INDEX idx_st_sla_ack_due ON support.support_ticket(sla_ack_due)
        WHERE first_response_at IS NULL AND status NOT IN ('resolved','closed')
        """
    )
    op.execute(
        """
        CREATE INDEX idx_st_sla_resolve_due ON support.support_ticket(sla_resolve_due)
        WHERE resolved_at IS NULL AND status NOT IN ('resolved','closed')
        """
    )

    # -------------------------------------------------------------------------
    # support.support_ticket_event
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE support.support_ticket_event (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ticket_id   UUID NOT NULL
                            REFERENCES support.support_ticket(id) ON DELETE CASCADE,
            kind        TEXT NOT NULL CHECK (kind IN (
                            'created','reply','status_change','resolution',
                            'csat','sla_breach','sla_resolve_breached','assignment')),
            actor       TEXT NOT NULL CHECK (actor IN ('user','agent','system')),
            actor_id    UUID,
            body        TEXT,
            metadata    JSONB,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_ste_ticket_id ON support.support_ticket_event(ticket_id)"
    )
    op.execute(
        "CREATE INDEX idx_ste_kind ON support.support_ticket_event(ticket_id, kind)"
    )

    # -------------------------------------------------------------------------
    # support.support_csat
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE support.support_csat (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ticket_id   UUID NOT NULL UNIQUE
                            REFERENCES support.support_ticket(id) ON DELETE CASCADE,
            score       SMALLINT NOT NULL CHECK (score BETWEEN 1 AND 5),
            comment     TEXT CHECK (char_length(comment) <= 1000),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # -------------------------------------------------------------------------
    # support.kb_article  (pgvector)
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE support.kb_article (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug        TEXT NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9\\-]+$'),
            title       TEXT NOT NULL,
            body_md     TEXT NOT NULL,
            tags        TEXT[] NOT NULL DEFAULT '{}',
            embedding   vector(3072),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_kb_tags ON support.kb_article USING GIN(tags)"
    )
    # ivfflat cosine index (lists=100; re-cluster when articles > 500)
    op.execute(
        """
        CREATE INDEX idx_kb_embedding ON support.kb_article
        USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
        """
    )

    # -------------------------------------------------------------------------
    # support.chatbot_session
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE support.chatbot_session (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL,
            ticket_id       UUID REFERENCES support.support_ticket(id),
            turn_count      SMALLINT NOT NULL DEFAULT 0,
            last_message_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at      TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '1 hour'
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_cs_user_id ON support.chatbot_session(user_id)"
    )
    op.execute(
        "CREATE INDEX idx_cs_expires_at ON support.chatbot_session(expires_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS support.chatbot_session CASCADE")
    op.execute("DROP TABLE IF EXISTS support.kb_article CASCADE")
    op.execute("DROP TABLE IF EXISTS support.support_csat CASCADE")
    op.execute("DROP TABLE IF EXISTS support.support_ticket_event CASCADE")
    op.execute("DROP TABLE IF EXISTS support.support_ticket CASCADE")
    op.execute("DROP SCHEMA IF EXISTS support CASCADE")
