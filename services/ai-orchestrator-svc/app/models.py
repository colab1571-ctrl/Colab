"""
ai-orchestrator-svc SQLAlchemy ORM models.

All tables live in the `ai` Postgres schema.
Tables:
  - MockupConsent: bilateral consent for AI Collab Preview
  - MockupAsset: generated image/audio asset with watermark metadata
  - AIInteraction: log of every AI command invocation
  - MockupScreenshotAudit: iOS screenshot detection audit log
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
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

ConsentStatusEnum = Enum(
    "pending_b", "approved", "rejected", "expired", "generated",
    name="mockup_consent_status", schema="ai",
)

GenerationKindEnum = Enum(
    "image", "audio", "both",
    name="generation_kind", schema="ai",
)

AssetKindEnum = Enum(
    "image", "audio",
    name="mockup_asset_kind", schema="ai",
)

ModerationStatusEnum = Enum(
    "passed", "blocked",
    name="mockup_moderation_status", schema="ai",
)

AICommandEnum = Enum(
    "mockup_image", "mockup_audio", "summarize_chat", "brainstorm", "palette",
    name="ai_command", schema="ai",
)

AIInteractionStatusEnum = Enum(
    "queued", "processing", "completed", "failed",
    "moderation_blocked", "refunded", "rejected_insufficient_credits",
    name="ai_interaction_status", schema="ai",
)

ScreenshotPlatformEnum = Enum(
    "ios", "android",
    name="screenshot_platform", schema="ai",
)


# ---------------------------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    __allow_unmapped__ = True


# ---------------------------------------------------------------------------
# MockupConsent
# ---------------------------------------------------------------------------

class MockupConsent(Base):
    """Bilateral consent record for AI Collab Preview mockup generation."""

    __tablename__ = "mockup_consent"
    __table_args__ = (
        # Only one active/pending consent per collab at a time
        Index(
            "idx_mockup_consent_collab_active",
            "collab_id",
            postgresql_where="status IN ('pending_b', 'approved')",
        ),
        {"schema": "ai"},
    )

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    collab_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    requested_by: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)  # party A
    party_a_consented_at: datetime = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    party_b_consented_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    lifespan_days: int = Column(SmallInteger, nullable=False, default=1)  # 1 or 14
    brief: str = Column(String(500), nullable=False, default="")
    status: str = Column(ConsentStatusEnum, nullable=False, default="pending_b")
    generation_kind: str = Column(GenerationKindEnum, nullable=False, default="image")
    created_at: datetime = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: datetime = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    # Consent expires (party B has 48h to respond)
    expires_consent_at: datetime = Column(DateTime(timezone=True), nullable=False)

    assets: list[MockupAsset] = relationship("MockupAsset", back_populates="consent", lazy="noload")


# ---------------------------------------------------------------------------
# MockupAsset
# ---------------------------------------------------------------------------

class MockupAsset(Base):
    """Generated AI mockup asset — image or audio, watermarked, stored in S3."""

    __tablename__ = "mockup_asset"
    __table_args__ = (
        Index("idx_mockup_asset_consent_id", "mockup_consent_id"),
        Index("idx_mockup_asset_expires_active", "expires_at", postgresql_where="active = true"),
        Index("idx_mockup_asset_replicate_id", "replicate_prediction_id"),
        {"schema": "ai"},
    )

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    mockup_consent_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=True)  # nullable for direct slash-command assets
    replicate_prediction_id: str = Column(String(64), nullable=False, unique=True)
    kind: str = Column(AssetKindEnum, nullable=False)
    s3_key: str = Column(Text, nullable=False)
    watermark_meta: dict = Column(JSONB, nullable=False, server_default="{}")
    moderation_score: float | None = Column(Numeric(4, 3), nullable=True)
    moderation_status: str | None = Column(ModerationStatusEnum, nullable=True)
    generated_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    expires_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    active: bool = Column(Boolean, nullable=False, default=True)
    file_size_bytes: int | None = Column(BigInteger, nullable=True)
    duration_ms: int | None = Column(Integer, nullable=True)  # audio only
    width: int | None = Column(Integer, nullable=True)         # image only
    height: int | None = Column(Integer, nullable=True)        # image only

    consent: MockupConsent | None = relationship("MockupConsent", back_populates="assets", lazy="noload")


# ---------------------------------------------------------------------------
# AIInteraction
# ---------------------------------------------------------------------------

class AIInteraction(Base):
    """Log of every AI command invocation — credit ledger anchor."""

    __tablename__ = "ai_interaction"
    __table_args__ = (
        Index("idx_ai_interaction_user_created", "user_id", "created_at"),
        Index("idx_ai_interaction_replicate_id", "replicate_prediction_id"),
        {"schema": "ai"},
    )

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    collab_id: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)
    room_id: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)
    command: str = Column(AICommandEnum, nullable=False)
    args_json: dict = Column(JSONB, nullable=False, server_default="{}")
    input_tokens: int | None = Column(Integer, nullable=True)
    output_tokens: int | None = Column(Integer, nullable=True)
    cost_credits: int = Column(Integer, nullable=False, default=0)
    replicate_prediction_id: str | None = Column(String(64), nullable=True)
    mockup_asset_id: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)
    billing_reservation_id: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)
    status: str = Column(AIInteractionStatusEnum, nullable=False, default="queued")
    failure_reason: str | None = Column(Text, nullable=True)
    created_at: datetime = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: datetime | None = Column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# MockupScreenshotAudit
# ---------------------------------------------------------------------------

class MockupScreenshotAudit(Base):
    """Audit log for iOS screenshot detection events. Retained indefinitely."""

    __tablename__ = "mockup_screenshot_audit"
    __table_args__ = (
        Index("idx_screenshot_audit_asset_id", "mockup_asset_id"),
        Index("idx_screenshot_audit_user_id", "user_id"),
        {"schema": "ai"},
    )

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    mockup_asset_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    user_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    platform: str = Column(ScreenshotPlatformEnum, nullable=False)
    detected_at: datetime = Column(DateTime(timezone=True), nullable=False)
    raw_event: dict = Column(JSONB, nullable=False, server_default="{}")
