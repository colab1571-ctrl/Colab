"""
profile-svc — ORM models.

Tables:
  profiles, profile_vocations, profile_skills, portfolio_items,
  external_links, personality_answers, personality_questions,
  profile_reviews, vocation_taxonomy, webhook_receipts
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geography
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Badge state enum values (stored as text + CHECK constraint)
# ---------------------------------------------------------------------------

BADGE_STATES = (
    "unverified",
    "email_verified",
    "identity_pending",
    "identity_approved",
    "ai_review_pending",
    "badge_granted",
    "badge_held",
    "badge_revoked",
)

PORTFOLIO_TYPES = ("image", "audio", "video", "link")
EXTERNAL_PROVIDERS = ("instagram", "youtube", "spotify")
AI_REVIEW_STATUSES = ("pending", "passed", "flagged", "hidden")
REVIEW_STATUSES = ("passed", "flagged", "escalated", "overridden")
REVIEW_KINDS = ("text", "image", "video", "audio")
REVIEW_TARGET_KINDS = ("profile_text", "portfolio_item", "display_name", "bio")
SYNC_STATES = ("ok", "needs_reauth", "revoked")
RADIUS_UNITS = ("mi", "km")

PERSONALITY_ARCHETYPES = (
    "architect",
    "craftsperson",
    "mystic",
    "maverick",
    "connector",
    "storyteller",
    "producer",
    "showrunner",
)


class Profile(Base):
    """Core profile record — owned by profile-svc."""

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("char_length(bio) <= 280", name="ck_profiles_bio_len"),
        CheckConstraint("char_length(obsessed_with) <= 140", name="ck_profiles_obsessed_len"),
        CheckConstraint("radius_value >= 1 AND radius_value <= 9999", name="ck_profiles_radius"),
        CheckConstraint("experience_level >= 1 AND experience_level <= 5", name="ck_profiles_exp"),
        CheckConstraint("profile_health_score >= 0 AND profile_health_score <= 100", name="ck_profiles_health"),
        CheckConstraint(f"badge_state IN {BADGE_STATES}", name="ck_profiles_badge_state"),
        CheckConstraint(f"radius_unit IN ('mi','km')", name="ck_profiles_radius_unit"),
        UniqueConstraint("user_id", name="uq_profiles_user_id"),
        Index("ix_profiles_badge_state", "badge_state"),
        Index("ix_profiles_health_desc", "profile_health_score", postgresql_ops={"profile_health_score": "DESC"}),
        Index("ix_profiles_last_active", "last_active_at", postgresql_ops={"last_active_at": "DESC"}),
        # Partial: badge_granted + visible to non-premium — backs free-tier discovery
        Index(
            "ix_profiles_discovery",
            "badge_state",
            "is_visible_to_non_premium",
            postgresql_where=text("badge_state = 'badge_granted' AND is_visible_to_non_premium = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # citext not natively supported here; use Text + application-level lowercasing + DB unique idx
    display_name: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    obsessed_with: Mapped[str | None] = mapped_column(Text, nullable=True)
    looking_for: Mapped[str | None] = mapped_column(Text, nullable=True)
    past_experience: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Location
    location_point: Mapped[Any | None] = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    location_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location_country: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # Radius — 9999 = "Anywhere"
    radius_value: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    radius_unit: Mapped[str] = mapped_column(String(2), nullable=False, default="mi")

    open_to_remote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    experience_level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    personality_archetype: Mapped[str | None] = mapped_column(String(32), nullable=True)

    profile_health_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    badge_state: Mapped[str] = mapped_column(String(32), nullable=False, default="unverified")
    badge_granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    badge_held_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_visible_to_non_premium: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # pgvector 1536-d embedding (text-embedding-3-large at dimensions=1536)
    embedding: Mapped[Any | None] = mapped_column(Vector(1536), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    vocations: Mapped[list[ProfileVocation]] = relationship(
        "ProfileVocation", back_populates="profile", cascade="all, delete-orphan", lazy="selectin"
    )
    skills: Mapped[list[ProfileSkill]] = relationship(
        "ProfileSkill", back_populates="profile", cascade="all, delete-orphan", lazy="selectin"
    )
    portfolio_items: Mapped[list[PortfolioItem]] = relationship(
        "PortfolioItem", back_populates="profile", cascade="all, delete-orphan", lazy="selectin",
        order_by="PortfolioItem.position",
    )
    external_links: Mapped[list[ExternalLink]] = relationship(
        "ExternalLink", back_populates="profile", cascade="all, delete-orphan", lazy="selectin"
    )
    personality_answers: Mapped[list[PersonalityAnswer]] = relationship(
        "PersonalityAnswer", back_populates="profile", cascade="all, delete-orphan", lazy="selectin"
    )
    reviews: Mapped[list[ProfileReview]] = relationship(
        "ProfileReview", back_populates="profile", cascade="all, delete-orphan", lazy="raise"
    )


class ProfileVocation(Base):
    __tablename__ = "profile_vocations"
    __table_args__ = (
        UniqueConstraint("profile_id", "category", name="uq_vocations_profile_category"),
        # Exactly one primary vocation per profile
        Index(
            "uix_vocations_primary",
            "profile_id",
            unique=True,
            postgresql_where=text("is_primary = true"),
        ),
        Index("ix_vocations_subtag", "subtag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    subtag: Mapped[str] = mapped_column(String(128), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    flagged_for_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    profile: Mapped[Profile] = relationship("Profile", back_populates="vocations")


class ProfileSkill(Base):
    __tablename__ = "profile_skills"
    __table_args__ = (
        UniqueConstraint("profile_id", "label_lower", name="uq_skills_profile_label"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    label_raw: Mapped[str] = mapped_column(String(40), nullable=False)
    label_lower: Mapped[str] = mapped_column(String(40), nullable=False)  # lowercased for uniqueness
    label_normalized: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    profile: Mapped[Profile] = relationship("Profile", back_populates="skills")


class PortfolioItem(Base):
    __tablename__ = "portfolio_items"
    __table_args__ = (
        UniqueConstraint("profile_id", "position", name="uq_portfolio_profile_position"),
        CheckConstraint("position >= 0 AND position <= 11", name="ck_portfolio_position"),
        CheckConstraint("size_bytes >= 0", name="ck_portfolio_size"),
        CheckConstraint(f"type IN ('image','audio','video','link')", name="ck_portfolio_type"),
        CheckConstraint(
            f"ai_review_status IN ('pending','passed','flagged','hidden')",
            name="ck_portfolio_ai_status",
        ),
        Index("ix_portfolio_profile_id", "profile_id"),
        # Partial index: only passed items served publicly
        Index(
            "ix_portfolio_passed",
            "profile_id",
            postgresql_where=text("ai_review_status = 'passed'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(8), nullable=False)
    s3_bucket: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    mime: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    caption: Mapped[str | None] = mapped_column(String(200), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Perceptual hashes (image)
    phash: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ahash: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Audio fingerprint
    chromaprint_fp: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Content embedding for semantic dup detection
    embedding: Mapped[Any | None] = mapped_column(Vector(1536), nullable=True)

    ai_review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    ai_review_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_review_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    profile: Mapped[Profile] = relationship("Profile", back_populates="portfolio_items")


class ExternalLink(Base):
    __tablename__ = "external_links"
    __table_args__ = (
        UniqueConstraint("profile_id", "provider", name="uq_external_profile_provider"),
        CheckConstraint(f"provider IN ('instagram','youtube','spotify')", name="ck_external_provider"),
        CheckConstraint(f"sync_state IN ('ok','needs_reauth','revoked')", name="ck_external_sync_state"),
        Index("ix_external_profile_id", "profile_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # KMS envelope encryption: iv||ciphertext||tag stored as bytea
    encrypted_access_token: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    encrypted_refresh_token: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    # KMS-wrapped DEK
    data_key_ciphertext: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)

    scopes: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_state: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")

    profile: Mapped[Profile] = relationship("Profile", back_populates="external_links")


class PersonalityAnswer(Base):
    __tablename__ = "personality_answers"
    __table_args__ = (
        UniqueConstraint("profile_id", "question_key", name="uq_personality_profile_question"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    question_key: Mapped[str] = mapped_column(String(64), nullable=False)
    answer_key: Mapped[str] = mapped_column(String(64), nullable=False)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    profile: Mapped[Profile] = relationship("Profile", back_populates="personality_answers")


class PersonalityQuestion(Base):
    """Admin-editable quiz question seed."""
    __tablename__ = "personality_questions"

    question_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict] = mapped_column(JSONB, nullable=False)  # [{answer_key, label, weights:{archetype:float}}]
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProfileReview(Base):
    __tablename__ = "profile_reviews"
    __table_args__ = (
        CheckConstraint(f"kind IN ('text','image','video','audio')", name="ck_review_kind"),
        CheckConstraint(
            f"target_kind IN ('profile_text','portfolio_item','display_name','bio')",
            name="ck_review_target_kind",
        ),
        CheckConstraint(
            f"status IN ('passed','flagged','escalated','overridden')",
            name="ck_review_status",
        ),
        CheckConstraint("score >= 0 AND score <= 1", name="ck_review_score"),
        Index("ix_reviews_profile_created", "profile_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reasons: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_versions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped[Profile] = relationship("Profile", back_populates="reviews")


class VocationTaxonomy(Base):
    """Admin-editable vocation taxonomy lookup table."""
    __tablename__ = "vocation_taxonomy"

    category: Mapped[str] = mapped_column(String(64), primary_key=True)
    subtag: Mapped[str] = mapped_column(String(128), primary_key=True)
    display: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class WebhookReceipt(Base):
    """Idempotency store for inbound webhooks (Replicate etc.)."""
    __tablename__ = "webhook_receipts"

    provider: Mapped[str] = mapped_column(String(64), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
