"""
identity-svc — ORM models.

IdentityVerification: Persona inquiry state per user.
PersonaWebhookEvent: Idempotency log for Persona webhook deliveries.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from colab_common.db import Base


class IdentityVerification(Base):
    """Tracks Persona selfie/liveness verification state per user."""

    __tablename__ = "identity_verifications"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_identity_verifications_user_id"),
        Index("ix_identity_verifications_persona_inquiry_id", "persona_inquiry_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    persona_inquiry_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # pending | approved | declined | needs_review
    status: Mapped[str] = mapped_column(
        Enum("pending", "approved", "declined", "needs_review", name="identity_status_enum"),
        default="pending",
        nullable=False,
    )

    # Face age signal from Persona: an estimated age value or None
    face_age_signal: Mapped[str | None] = mapped_column(String(32), nullable=True)

    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Raw Persona webhook payload stored as JSONB for audit
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PersonaWebhookEvent(Base):
    """
    Idempotency log for Persona webhook deliveries.
    Persona has at-least-once semantics; we deduplicate on event_id.
    """

    __tablename__ = "persona_webhook_events"
    __table_args__ = (UniqueConstraint("event_id", name="uq_persona_webhook_event_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_name: Mapped[str] = mapped_column(String(128), nullable=False)
    inquiry_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
