"""
discovery-svc — ORM models.

Tables (all in `discovery` schema):
  hide_3mo, saved_profiles, feed_preferences
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Hide3mo(Base):
    """A viewer's decision to hide a profile for 90 days."""

    __tablename__ = "hide_3mo"
    __table_args__ = (
        UniqueConstraint("user_id", "hidden_profile_id", name="uq_hide3mo_user_profile"),
        Index("ix_hide3mo_user_until", "user_id", "hidden_until"),
        {"schema": "discovery"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    hidden_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    hidden_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    hidden_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SavedProfile(Base):
    """A viewer's saved / liked profile."""

    __tablename__ = "saved_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "saved_profile_id", name="uq_saved_user_profile"),
        Index("ix_saved_user_at", "user_id", "saved_at"),
        {"schema": "discovery"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    saved_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FeedPreference(Base):
    """Per-user feed mode preference (scroll | swipe)."""

    __tablename__ = "feed_preferences"
    __table_args__ = (
        CheckConstraint("mode IN ('scroll','swipe')", name="ck_feed_pref_mode"),
        {"schema": "discovery"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="scroll")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
