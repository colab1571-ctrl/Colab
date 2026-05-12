"""
auth-svc — ORM models: User, Identity, Session, LegalAcceptance, MagicLink.

LoginAttempt is Redis-backed (not Postgres) per spec §owned-entities.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from colab_common.db import Base


class User(Base):
    """Core user record — auth state only. Profile data lives in profile-svc."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_status: Mapped[str] = mapped_column(
        Enum("active", "bounced", "complained", name="email_status_enum", create_type=False),
        default="active",
        nullable=False,
    )
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True, index=True)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # argon2id encoded hash; NULL for OAuth-only accounts
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_hash_version: Mapped[int] = mapped_column(default=1, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Forward-compatible MFA columns (not active at launch)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    identities: Mapped[list[Identity]] = relationship("Identity", back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[list[Session]] = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    legal_acceptances: Mapped[list[LegalAcceptance]] = relationship(
        "LegalAcceptance", back_populates="user", cascade="all, delete-orphan"
    )
    magic_links: Mapped[list[MagicLink]] = relationship(
        "MagicLink", back_populates="user", cascade="all, delete-orphan"
    )


class Identity(Base):
    """OAuth federation records. One user can have multiple identities (apple, google, phone)."""

    __tablename__ = "identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uq_identities_provider_subject"),
        Index("ix_identities_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(
        Enum("apple", "google", "email", "phone", name="identity_provider_enum", create_type=False), nullable=False
    )
    provider_subject: Mapped[str] = mapped_column(String(512), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="identities")


class Session(Base):
    """Active refresh-token sessions. Soft-deleted via revoked_at."""

    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # SHA-256(refresh_token_bytes) — never store raw token
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # JTI of the current refresh token for replay detection
    refresh_jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 max
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="sessions")


class LegalAcceptance(Base):
    """Time-stamped, IP-stamped, version-stamped legal doc acceptance."""

    __tablename__ = "legal_acceptances"
    __table_args__ = (Index("ix_legal_acceptances_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    doc_type: Mapped[str] = mapped_column(
        Enum("tos", "privacy", "community_guidelines", name="doc_type_enum", create_type=False), nullable=False
    )
    doc_version: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="legal_acceptances")


class MagicLink(Base):
    """
    Single-use signed tokens for email verification, password reset,
    email/phone change flows. OTP 6-digit code for the same flow shares
    this row (both consume it).
    """

    __tablename__ = "magic_links"
    __table_args__ = (Index("ix_magic_links_token_hash", "token_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(
        Enum(
            "email_verify",
            "password_reset",
            "email_change",
            "phone_change",
            name="magic_link_purpose_enum",
            create_type=False,
        ),
        nullable=False,
    )
    # SHA-256(opaque_token_bytes) — never store raw token
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # 6-digit OTP alternative
    otp_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # For email_change / phone_change: the new value being confirmed
    new_value: Mapped[str | None] = mapped_column(String(255), nullable=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="magic_links")
