"""
admin-svc SQLAlchemy ORM models.

All tables live in the `admin` Postgres schema.
AdminAuditLog is append-only — enforced via REVOKE + trigger in the migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class AdminUser(Base):
    """Admin staff member. Must also exist in auth.user."""

    __tablename__ = "admin_user"
    __table_args__ = (
        Index("ix_admin_user_roles", "roles", postgresql_using="gin"),
        {"schema": "admin"},
    )

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # roles: subset of {mod, support, billing_admin, super_admin}
    roles = Column(ARRAY(String), nullable=False, default=list)
    status = Column(String(32), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by = Column(UUID(as_uuid=True), nullable=True)  # self-referential; null for bootstrap
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    mfa_enrolled_at = Column(DateTime(timezone=True), nullable=True)
    mfa_secret = Column(Text, nullable=True)  # encrypted TOTP secret


class AdminAuditLog(Base):
    """
    Append-only audit log.

    Postgres privileges: admin_svc_app has INSERT, SELECT only.
    REVOKE UPDATE, DELETE, TRUNCATE is applied in the Alembic migration.
    A trigger raises an exception on any attempt to mutate rows.
    """

    __tablename__ = "admin_audit_log"
    __table_args__ = (
        Index("ix_aal_admin_user_created", "admin_user_id", "created_at"),
        Index("ix_aal_target", "target_kind", "target_id", "created_at"),
        Index("ix_aal_action_created", "action_type", "created_at"),
        {"schema": "admin"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
                server_default=func.gen_random_uuid())
    admin_user_id = Column(UUID(as_uuid=True), nullable=False)
    action_type = Column(String(64), nullable=False)
    target_kind = Column(String(64), nullable=False)
    target_id = Column(Text, nullable=False)
    payload_before = Column(JSONB, nullable=True)
    payload_after = Column(JSONB, nullable=True)
    reason = Column(Text, nullable=True)
    ip = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FeatureFlag(Base):
    """Feature flag per (key, env). Mirrored to PostHog on write."""

    __tablename__ = "feature_flag"
    __table_args__ = (
        UniqueConstraint("key", "env", name="uq_feature_flag_key_env"),
        {"schema": "admin"},
    )

    key = Column(String(128), primary_key=True)
    env = Column(String(16), primary_key=True)
    value = Column(JSONB, nullable=False)
    canary_pct = Column(Numeric(5, 2), nullable=False, default=0)
    description = Column(Text, nullable=False)
    updated_by = Column(UUID(as_uuid=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EntitlementConfig(Base):
    """
    Source-of-truth for tier entitlement values.
    Append-only via effective_at/superseded_at versioning — rows are never updated.
    """

    __tablename__ = "entitlement_config"
    __table_args__ = (
        UniqueConstraint(
            "tier", "axis_key", "effective_at", name="uq_entitlement_tier_axis_effective"
        ),
        Index("ix_entitlement_tier_axis", "tier", "axis_key"),
        {"schema": "admin"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
                server_default=func.gen_random_uuid())
    tier = Column(String(32), nullable=False)
    axis_key = Column(String(64), nullable=False)
    value = Column(JSONB, nullable=False)
    currency = Column(String(3), nullable=True)
    effective_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
