"""Initial chat schema — chat_room, chat_message (monthly partitioned),
chat_message_revision, chat_attachment, chat_read_receipt.

Revision ID: 0001
Revises:
Create Date: 2026-05-11

Retention: chat_message is RANGE-partitioned by created_at (monthly).
pg_partman (or manual partition creation) adds new monthly partitions.
Rows are never hard-deleted; deleted_at used for soft-delete.
Archive partitions > 18 months to S3 via lifecycle Celery job.
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
    op.execute("CREATE SCHEMA IF NOT EXISTS chat")

    # -----------------------------------------------------------------------
    # Enums
    # -----------------------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE chat.room_state AS ENUM ('open', 'read_only', 'archived');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE chat.message_type AS ENUM (
                'text', 'voice', 'image', 'video', 'audio', 'doc', 'link', 'system'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE chat.moderation_status AS ENUM (
                'pending', 'allowed', 'soft_warn', 'hidden', 'auto_hidden'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    # -----------------------------------------------------------------------
    # chat_room
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE chat.chat_room (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collaboration_id UUID NOT NULL,
            participant_ids  UUID[2] NOT NULL,
            state            chat.room_state NOT NULL DEFAULT 'open',
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            archived_at      TIMESTAMPTZ,
            CONSTRAINT chk_two_participants CHECK (cardinality(participant_ids) = 2)
        )
    """)

    op.execute("""
        CREATE INDEX idx_chat_room_collaboration
            ON chat.chat_room(collaboration_id)
    """)
    op.execute("""
        CREATE INDEX idx_chat_room_participants
            ON chat.chat_room USING GIN(participant_ids)
    """)

    # -----------------------------------------------------------------------
    # chat_message — RANGE partitioned by created_at (monthly)
    # Note: UUIDv7 as primary key — time-ordered, embeds epoch ms
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE chat.chat_message (
            id                  UUID NOT NULL,
            room_id             UUID NOT NULL REFERENCES chat.chat_room(id),
            sender_profile_id   UUID NOT NULL,
            type                chat.message_type NOT NULL,
            body                TEXT,
            media_key           TEXT,
            mime                TEXT,
            size_bytes          BIGINT,
            duration_ms         INTEGER,
            reply_to            UUID,
            client_nonce        UUID,
            edited_at           TIMESTAMPTZ,
            deleted_at          TIMESTAMPTZ,
            moderation_score    REAL,
            moderation_status   chat.moderation_status NOT NULL DEFAULT 'pending',
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    # Seed initial monthly partitions: 2026-05 through 2026-12
    for y, m in [
        (2026, 5), (2026, 6), (2026, 7), (2026, 8),
        (2026, 9), (2026, 10), (2026, 11), (2026, 12),
    ]:
        nm = m + 1 if m < 12 else 1
        ny = y if m < 12 else y + 1
        op.execute(f"""
            CREATE TABLE chat.chat_message_{y}{m:02d}
            PARTITION OF chat.chat_message
            FOR VALUES FROM ('{y}-{m:02d}-01') TO ('{ny}-{nm:02d}-01')
        """)

    op.execute("""
        CREATE INDEX idx_chat_msg_room_id
            ON chat.chat_message(room_id, id)
    """)
    op.execute("""
        CREATE INDEX idx_chat_msg_sender
            ON chat.chat_message(sender_profile_id)
    """)
    op.execute("""
        CREATE INDEX idx_chat_msg_nonce
            ON chat.chat_message(client_nonce)
            WHERE client_nonce IS NOT NULL
    """)

    # -----------------------------------------------------------------------
    # chat_message_revision
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE chat.chat_message_revision (
            id        BIGSERIAL PRIMARY KEY,
            msg_id    UUID NOT NULL,
            version   SMALLINT NOT NULL,
            body      TEXT NOT NULL,
            edited_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (msg_id, version)
        )
    """)

    # -----------------------------------------------------------------------
    # chat_attachment
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE chat.chat_attachment (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            msg_id                UUID NOT NULL,
            kind                  TEXT NOT NULL,
            s3_key                TEXT NOT NULL,
            signed_url_cache_until TIMESTAMPTZ,
            signed_url_cache      TEXT
        )
    """)

    # -----------------------------------------------------------------------
    # chat_read_receipt
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE chat.chat_read_receipt (
            room_id          UUID NOT NULL REFERENCES chat.chat_room(id),
            profile_id       UUID NOT NULL,
            last_read_msg_id UUID,
            last_read_at     TIMESTAMPTZ,
            PRIMARY KEY (room_id, profile_id)
        )
    """)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS chat CASCADE")
