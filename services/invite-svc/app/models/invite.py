"""
invite-svc — ORM models.

Tables (schema: invite):
  collab_invite  — Vibe Check lifecycle records (never deleted)
  block          — Bidirectional block registry
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enum value sets (stored as TEXT + CHECK constraints per colab convention)
# ---------------------------------------------------------------------------

INVITE_STATUSES = ("pending", "accepted", "rejected", "expired", "cancelled")
BLOCK_REASONS = ("harassment", "spam", "inappropriate_content", "other")


class CollabInvite(Base):
    """
    A Vibe Check invite from one profile to another.

    State machine:
      pending → accepted | rejected | expired | cancelled
    Rows are NEVER deleted; terminal states are archived history (Journey G).
    """

    __tablename__ = "collab_invite"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','accepted','rejected','expired','cancelled')",
            name="ck_invite_status",
        ),
        CheckConstraint(
            "char_length(synopsis) <= 250",
            name="ck_invite_synopsis_len",
        ),
        CheckConstraint(
            "from_profile_id <> to_profile_id",
            name="ck_invite_no_self_invite",
        ),
        CheckConstraint(
            "ai_match_score IS NULL OR (ai_match_score >= 0 AND ai_match_score <= 1)",
            name="ck_invite_ai_score_range",
        ),
        # Inbox query: recipient + status + recency
        Index("ix_invite_to_status_created", "to_profile_id", "status", "created_at"),
        # Sent query: sender + status + recency
        Index("ix_invite_from_status_created", "from_profile_id", "status", "created_at"),
        # TTL Celery Beat job: pending rows past archive_at
        Index(
            "ix_invite_ttl_job",
            "status",
            "archive_at",
            postgresql_where=text("status = 'pending'"),
        ),
        # Idempotency: prevent exact duplicate sends within dedup window
        # (from, to, synopsis_hash) uniqueness enforced in application layer via Redis
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    from_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    to_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    synopsis: Mapped[str] = mapped_column(String(250), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")

    # Snapshot of AI match score from matching-svc at send time (§005)
    ai_match_score: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    # FK to moderation_case if synopsis was flagged (cross-service reference)
    mod_case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # archive_at = created_at + 30 days — set at insert; TTL job uses this
    archive_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Idempotency key stored for replay protection (client X-Idempotency-Key)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)


class Block(Base):
    """
    One-way block write with two-way effect:
      block(A→B): A cannot see B, B cannot see A in any surface.
    Both block(A,B) and block(B,A) may coexist independently.
    Only the blocker can remove the block.
    """

    __tablename__ = "block"
    __table_args__ = (
        CheckConstraint(
            "reason IS NULL OR reason IN ('harassment','spam','inappropriate_content','other')",
            name="ck_block_reason",
        ),
        CheckConstraint(
            "blocker_id <> blocked_id",
            name="ck_block_no_self_block",
        ),
        # Composite PK enforces uniqueness; reverse lookup index:
        Index("ix_block_blocked_id", "blocked_id"),
    )

    blocker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )
    blocked_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Nullable reason enum (stored as text per colab convention)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
