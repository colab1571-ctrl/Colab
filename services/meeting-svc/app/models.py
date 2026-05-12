"""
meeting-svc SQLAlchemy ORM models.

All tables live in the `meeting` Postgres schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

MeetingStatusEnum = Enum(
    "scheduled", "started", "ended", "cancelled",
    name="meeting_status",
    schema="meeting",
)

BotStatusEnum = Enum(
    "none", "requested", "joining", "joined", "left", "failed",
    name="bot_status",
    schema="meeting",
)

ArtifactKindEnum = Enum(
    "transcript", "recording", "summary",
    name="artifact_kind",
    schema="meeting",
)


# ---------------------------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    __allow_unmapped__ = True


# ---------------------------------------------------------------------------
# Meeting
# ---------------------------------------------------------------------------


class Meeting(Base):
    __tablename__ = "meeting"
    __table_args__ = (
        Index("idx_meeting_collab", "collab_id"),
        Index(
            "idx_meeting_scheduled",
            "scheduled_at",
            postgresql_where="status = 'scheduled'",
        ),
        {"schema": "meeting"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    collab_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    organizer_profile_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    scheduled_at: datetime = Column(DateTime(timezone=True), nullable=False)
    duration_min: int = Column(SmallInteger, nullable=False, default=60)
    join_url: str = Column(Text, nullable=False)
    ics_s3_key: str | None = Column(Text, nullable=True)
    gcal_event_id: str | None = Column(Text, nullable=True)
    gcal_request_id: uuid.UUID = Column(
        UUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4
    )
    status: str = Column(
        MeetingStatusEnum, nullable=False, default="scheduled"
    )
    bot_enabled: bool = Column(Boolean, nullable=False, default=False)
    bot_status: str = Column(BotStatusEnum, nullable=False, default="none")
    recall_bot_id: str | None = Column(Text, nullable=True)
    cancelled_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    artifacts: list[MeetingArtifact] = relationship(
        "MeetingArtifact", back_populates="meeting", lazy="selectin"
    )
    consents: list[MeetingBotConsent] = relationship(
        "MeetingBotConsent", back_populates="meeting", lazy="selectin"
    )


# ---------------------------------------------------------------------------
# MeetingArtifact
# ---------------------------------------------------------------------------


class MeetingArtifact(Base):
    __tablename__ = "meeting_artifact"
    __table_args__ = (
        Index("idx_artifact_meeting", "meeting_id"),
        {"schema": "meeting"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    meeting_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("meeting.meeting.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: str = Column(ArtifactKindEnum, nullable=False)
    s3_key: str = Column(Text, nullable=False)
    size_bytes: int | None = Column(BigInteger, nullable=True)
    ready_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    meeting: Meeting = relationship("Meeting", back_populates="artifacts")


# ---------------------------------------------------------------------------
# MeetingBotConsent
# ---------------------------------------------------------------------------


class MeetingBotConsent(Base):
    __tablename__ = "meeting_bot_consent"
    __table_args__ = (
        UniqueConstraint("meeting_id", "profile_id", name="uq_consent_meeting_profile"),
        Index("idx_consent_meeting", "meeting_id"),
        {"schema": "meeting"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    meeting_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("meeting.meeting.id", ondelete="CASCADE"),
        nullable=False,
    )
    profile_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    consented_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: datetime | None = Column(DateTime(timezone=True), nullable=True)

    meeting: Meeting = relationship("Meeting", back_populates="consents")
