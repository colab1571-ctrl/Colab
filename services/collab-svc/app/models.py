"""
collab-svc SQLAlchemy ORM models.

All tables live in the `collab` Postgres schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

CollabStatusEnum = Enum(
    "still_deciding",
    "in_progress",
    "completed",
    "didnt_work_out",
    name="collab_status",
    schema="collab",
)

FeedbackRatingEnum = Enum(
    "up",
    "down",
    name="feedback_rating",
    schema="collab",
)

FeedbackTargetEnum = Enum(
    "project",
    "partner",
    name="feedback_target",
    schema="collab",
)

FeedbackTagEnum = Enum(
    "communicative",
    "responsive",
    "professional",
    "creative",
    "reliable",
    "flexible",
    "ghosted",
    "slow_to_respond",
    "missed_deadlines",
    "scope_creep",
    "great_outcome",
    "met_goals",
    "learned_a_lot",
    "good_creative_fit",
    "incomplete",
    "unclear_direction",
    "changed_scope",
    "technical_issues",
    name="feedback_tag",
    schema="collab",
)

ExportStatusEnum = Enum(
    "pending",
    "generating",
    "ready",
    "failed",
    name="export_status",
    schema="collab",
)


# ---------------------------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Collaboration
# ---------------------------------------------------------------------------


class Collaboration(Base):
    __tablename__ = "collaboration"
    __table_args__ = (
        UniqueConstraint(
            "least_participant",
            "greatest_participant",
            name="collaboration_participants_unique",
        ),
        Index("idx_collaboration_search_vector", "search_vector", postgresql_using="gin"),
        Index("idx_collaboration_profile_a", "profile_id_a"),
        Index("idx_collaboration_profile_b", "profile_id_b"),
        Index("idx_collaboration_status", "status"),
        Index("idx_collaboration_last_activity", "last_activity_at"),
        {"schema": "collab"},
    )

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    profile_id_a: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    profile_id_b: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    # Denormalized LEAST/GREATEST for unique constraint (order-independent)
    least_participant: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    greatest_participant: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    title: str | None = Column(Text, nullable=True)
    description: str | None = Column(Text, nullable=True)
    status: str = Column(CollabStatusEnum, nullable=False, default="still_deciding")
    is_read_only: bool = Column(Boolean, nullable=False, default=False)
    last_activity_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    nudge_sent_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    archive_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    archived_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    completed_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    search_vector: str | None = Column(TSVECTOR, nullable=True)

    status_events: list[CollabStatusEvent] = relationship(
        "CollabStatusEvent", back_populates="collab", lazy="noload"
    )
    feedback: list[CollabFeedback] = relationship(
        "CollabFeedback", back_populates="collab", lazy="noload"
    )
    exports: list[CollabExport] = relationship(
        "CollabExport", back_populates="collab", lazy="noload"
    )
    file_names: list[CollabFileName] = relationship(
        "CollabFileName", back_populates="collab", lazy="noload"
    )
    name_cache: list[CollabParticipantNameCache] = relationship(
        "CollabParticipantNameCache", back_populates="collab", lazy="noload"
    )


# ---------------------------------------------------------------------------
# CollabStatusEvent
# ---------------------------------------------------------------------------


class CollabStatusEvent(Base):
    __tablename__ = "collab_status_event"
    __table_args__ = (
        Index("idx_collab_status_event_collab", "collab_id", "created_at"),
        {"schema": "collab"},
    )

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    collab_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("collab.collaboration.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_profile_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    prev_status: str = Column(Text, nullable=False)
    new_status: str = Column(Text, nullable=False)
    note: str | None = Column(Text, nullable=True)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    collab: Collaboration = relationship("Collaboration", back_populates="status_events")


# ---------------------------------------------------------------------------
# CollabFeedback
# ---------------------------------------------------------------------------


class CollabFeedback(Base):
    __tablename__ = "collab_feedback"
    __table_args__ = (
        UniqueConstraint(
            "collab_id", "from_profile_id", "target",
            name="collab_feedback_unique",
        ),
        Index("idx_collab_feedback_collab", "collab_id"),
        Index("idx_collab_feedback_from", "from_profile_id"),
        {"schema": "collab"},
    )

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    collab_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("collab.collaboration.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_profile_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    to_profile_id: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)
    target: str = Column(FeedbackTargetEnum, nullable=False)
    rating: str = Column(FeedbackRatingEnum, nullable=False)
    tags: list[str] = Column(ARRAY(Text), nullable=False, default=list)
    comment: str | None = Column(Text, nullable=True)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    collab: Collaboration = relationship("Collaboration", back_populates="feedback")


# ---------------------------------------------------------------------------
# CollabExport
# ---------------------------------------------------------------------------


class CollabExport(Base):
    __tablename__ = "collab_export"
    __table_args__ = (
        Index("idx_collab_export_collab", "collab_id"),
        Index("idx_collab_export_requested_by", "requested_by"),
        {"schema": "collab"},
    )

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    collab_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("collab.collaboration.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_by: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    status: str = Column(ExportStatusEnum, nullable=False, default="pending")
    pdf_s3_key: str | None = Column(Text, nullable=True)
    zip_s3_key: str | None = Column(Text, nullable=True)
    error_detail: str | None = Column(Text, nullable=True)
    requested_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    completed_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    expires_at: datetime | None = Column(DateTime(timezone=True), nullable=True)

    collab: Collaboration = relationship("Collaboration", back_populates="exports")


# ---------------------------------------------------------------------------
# CollabFileName (search denormalization)
# ---------------------------------------------------------------------------


class CollabFileName(Base):
    __tablename__ = "collab_file_name"
    __table_args__ = (
        Index("idx_collab_file_name_collab", "collab_id"),
        {"schema": "collab"},
    )

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    collab_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("collab.collaboration.id", ondelete="CASCADE"),
        nullable=False,
    )
    s3_key: str = Column(Text, nullable=False)
    file_name: str = Column(Text, nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    collab: Collaboration = relationship("Collaboration", back_populates="file_names")


# ---------------------------------------------------------------------------
# CollabParticipantNameCache (for search_vector refresh without cross-schema joins)
# ---------------------------------------------------------------------------


class CollabParticipantNameCache(Base):
    __tablename__ = "collab_participant_name_cache"
    __table_args__ = (
        UniqueConstraint("collab_id", "profile_id", name="collab_name_cache_unique"),
        Index("idx_collab_name_cache_collab", "collab_id"),
        {"schema": "collab"},
    )

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    collab_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("collab.collaboration.id", ondelete="CASCADE"),
        nullable=False,
    )
    profile_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    display_name: str = Column(Text, nullable=False)
    updated_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    collab: Collaboration = relationship("Collaboration", back_populates="name_cache")
