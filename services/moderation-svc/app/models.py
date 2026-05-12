"""
moderation-svc SQLAlchemy ORM models.

All tables live in the `moderation` Postgres schema.
ModerationAction is append-only — see the Alembic migration for the
pg trigger that blocks UPDATE and DELETE.
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
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func

# ---------------------------------------------------------------------------
# Enums (postgres-native via SQLAlchemy Enum)
# ---------------------------------------------------------------------------

CaseKindEnum = Enum(
    "auto", "report", "dmca",
    name="case_kind", schema="moderation",
)

SubjectTypeEnum = Enum(
    "msg", "profile_field", "portfolio_item", "invite_synopsis", "mockup", "user",
    name="subject_type", schema="moderation",
)

CaseStatusEnum = Enum(
    "open", "in_review", "actioned", "dismissed", "escalated",
    name="case_status", schema="moderation",
)

PriorityTierEnum = Enum(
    "tier_0_allow", "tier_1_24h", "tier_2_6h", "tier_3_1h",
    name="priority_tier", schema="moderation",
)

ActionTypeEnum = Enum(
    "warn",
    "hide",
    "restore",
    "temp_mute_1h",
    "temp_mute_24h",
    "temp_mute_7d",
    "permanent_ban",
    "delete_account",
    "dismiss",
    "escalate_to_legal",
    name="action_type", schema="moderation",
)

PropagationStatusEnum = Enum(
    "pending", "partial", "complete", "failed",
    name="propagation_status", schema="moderation",
)

DMCAStateEnum = Enum(
    "received", "hidden", "counter_pending", "restored", "permanent", "rejected_defective",
    name="dmca_state", schema="moderation",
)

CounterNoticeStateEnum = Enum(
    "received", "awaiting_window", "restored", "permanent_taken_down",
    name="counter_notice_state", schema="moderation",
)


# ---------------------------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    __allow_unmapped__ = True


# ---------------------------------------------------------------------------
# ModerationCase
# ---------------------------------------------------------------------------


class ModerationCase(Base):
    __tablename__ = "moderation_cases"
    __table_args__ = (
        Index("ix_mod_case_queue", "status", "priority_tier", "sla_due_at"),
        Index("ix_mod_case_subject", "subject_type", "subject_id"),
        Index("ix_mod_case_owner", "subject_owner_user_id", "opened_at"),
        {"schema": "moderation"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    kind: str = Column(CaseKindEnum, nullable=False)
    subject_type: str = Column(SubjectTypeEnum, nullable=False)
    subject_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    subject_owner_user_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    reporter_user_id: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)

    score: float | None = Column(Numeric(3, 2), nullable=True)
    scores_breakdown: dict = Column(JSONB, nullable=False, server_default="{}")

    forced_human: bool = Column(Boolean, nullable=False, default=False)
    forced_reason: str | None = Column(String(200), nullable=True)

    status: str = Column(CaseStatusEnum, nullable=False, default="open")
    priority_tier: str = Column(PriorityTierEnum, nullable=False, default="tier_1_24h")

    sla_due_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    sla_breached_at: datetime | None = Column(DateTime(timezone=True), nullable=True)

    opened_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    claimed_by: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)
    claimed_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    actioned_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    actioned_by: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)
    action_type: str | None = Column(ActionTypeEnum, nullable=True)

    second_reviewer_id: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)

    # for upstream-retry de-dup of auto cases
    idempotency_key: str | None = Column(String(512), nullable=True, unique=True)

    parent_case_id: uuid.UUID | None = Column(
        UUID(as_uuid=True), ForeignKey("moderation.moderation_cases.id"), nullable=True
    )

    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    actions: list[ModerationAction] = relationship(
        "ModerationAction", back_populates="case", lazy="selectin"
    )
    reports: list[Report] = relationship("Report", back_populates="case", lazy="selectin")


# ---------------------------------------------------------------------------
# ModerationAction — APPEND-ONLY (DB trigger blocks UPDATE/DELETE)
# ---------------------------------------------------------------------------


class ModerationAction(Base):
    __tablename__ = "moderation_actions"
    __table_args__ = (
        Index("ix_mod_action_case", "case_id", "created_at"),
        Index("ix_mod_action_target", "target_user_id", "created_at"),
        {"schema": "moderation"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    case_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("moderation.moderation_cases.id"),
        nullable=False,
    )
    action_type: str = Column(ActionTypeEnum, nullable=False)
    reviewer_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    reason: str = Column(Text, nullable=False)  # min 12 chars enforced at API layer
    evidence_refs: list = Column(JSONB, nullable=False, server_default="[]")
    target_user_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)

    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    propagation_status: str = Column(
        PropagationStatusEnum, nullable=False, default="pending"
    )
    propagation_events: dict = Column(JSONB, nullable=False, server_default="{}")

    case: ModerationCase = relationship("ModerationCase", back_populates="actions")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_report_reporter", "reporter_user_id", "created_at"),
        Index("ix_report_subject", "subject_type", "subject_id"),
        {"schema": "moderation"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    reporter_user_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    subject_type: str = Column(SubjectTypeEnum, nullable=False)
    subject_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    description: str = Column(String(1000), nullable=False)
    screenshot_s3_key: str | None = Column(Text, nullable=True)
    case_id: uuid.UUID | None = Column(
        UUID(as_uuid=True),
        ForeignKey("moderation.moderation_cases.id"),
        nullable=True,
    )
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reporter_ip: str | None = Column(INET, nullable=True)
    device_id: str | None = Column(String(255), nullable=True)

    case: ModerationCase | None = relationship("ModerationCase", back_populates="reports")


# ---------------------------------------------------------------------------
# ReportThrottle — per-reporter daily cap
# ---------------------------------------------------------------------------


class ReportThrottle(Base):
    __tablename__ = "report_throttle"
    __table_args__ = (
        UniqueConstraint("reporter_user_id", "day", name="uq_report_throttle_user_day"),
        {"schema": "moderation"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    reporter_user_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    day: datetime = Column(DateTime(timezone=True), nullable=False)
    count: int = Column(Integer, nullable=False, default=0)


# ---------------------------------------------------------------------------
# DMCANotice
# ---------------------------------------------------------------------------


class DMCANotice(Base):
    __tablename__ = "dmca_notices"
    __table_args__ = (
        Index("ix_dmca_state", "state", "hide_at"),
        {"schema": "moderation"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    claimant_name: str = Column(String(200), nullable=False)
    claimant_address: str = Column(Text, nullable=False)
    claimant_phone: str = Column(String(40), nullable=False)
    claimant_email: str = Column(String(320), nullable=False)
    is_authorized_agent: bool = Column(Boolean, nullable=False)
    sworn_statement_text: str = Column(Text, nullable=False)
    signature_full_name: str = Column(String(200), nullable=False)
    hash_of_signature: bytes = Column(LargeBinary(32), nullable=False)
    copyrighted_work_description: str = Column(Text, nullable=False)
    copyrighted_work_url_or_registration: str | None = Column(Text, nullable=True)

    target_subject_type: str = Column(SubjectTypeEnum, nullable=False)
    target_subject_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    target_url_on_colab: str = Column(Text, nullable=False)
    target_user_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)

    claimant_ip: str | None = Column(INET, nullable=True)
    received_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    hide_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    hidden_at: datetime | None = Column(DateTime(timezone=True), nullable=True)

    state: str = Column(DMCAStateEnum, nullable=False, default="received")
    rejection_reason: str | None = Column(Text, nullable=True)

    case_id: uuid.UUID | None = Column(
        UUID(as_uuid=True),
        ForeignKey("moderation.moderation_cases.id"),
        nullable=True,
    )

    counter_notice: CounterNotice | None = relationship(
        "CounterNotice", back_populates="dmca_notice", uselist=False, lazy="selectin"
    )


# ---------------------------------------------------------------------------
# CounterNotice
# ---------------------------------------------------------------------------


class CounterNotice(Base):
    __tablename__ = "counter_notices"
    __table_args__ = (
        Index("ix_counter_window", "state", "statutory_window_end"),
        {"schema": "moderation"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    dmca_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("moderation.dmca_notices.id"),
        nullable=False,
        unique=True,
    )
    counter_claimant_user_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    counter_claimant_legal_name: str = Column(String(200), nullable=False)
    counter_claimant_address: str = Column(Text, nullable=False)
    counter_claimant_phone: str = Column(String(40), nullable=False)
    counter_statement_text: str = Column(Text, nullable=False)
    consent_to_jurisdiction: bool = Column(Boolean, nullable=False)
    consent_to_service_of_process: bool = Column(Boolean, nullable=False)
    signature_full_name: str = Column(String(200), nullable=False)
    hash_of_signature: bytes = Column(LargeBinary(32), nullable=False)

    received_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    statutory_window_end: datetime | None = Column(DateTime(timezone=True), nullable=True)
    forwarded_to_claimant_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    suit_filed_notice_received_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    restored_at: datetime | None = Column(DateTime(timezone=True), nullable=True)

    state: str = Column(CounterNoticeStateEnum, nullable=False, default="received")

    dmca_notice: DMCANotice = relationship(
        "DMCANotice", back_populates="counter_notice"
    )


# ---------------------------------------------------------------------------
# Banned registries
# ---------------------------------------------------------------------------


class BannedHashRegistry(Base):
    __tablename__ = "banned_hash_registry"
    __table_args__ = {"schema": "moderation"}

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    hash_phash: bytes = Column(LargeBinary(8), nullable=False, unique=True)
    source: str = Column(String(200), nullable=False)
    severity: str = Column(String(50), nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    notes: str | None = Column(Text, nullable=True)


class BannedAudioFingerprint(Base):
    __tablename__ = "banned_audio_fingerprints"
    __table_args__ = {"schema": "moderation"}

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    fingerprint: list[int] = Column(ARRAY(Integer), nullable=False)
    source: str = Column(String(200), nullable=False)
    severity: str = Column(String(50), nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BannedTextEmbedding(Base):
    __tablename__ = "banned_text_embeddings"
    __table_args__ = {"schema": "moderation"}

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # pgvector column — stored as TEXT in migration, cast with ::vector
    embedding_json: str = Column(Text, nullable=False)
    source: str = Column(String(200), nullable=False)
    severity: str = Column(String(50), nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# ModScanLog — every scan logged (30d online retention, then S3 archive)
# ---------------------------------------------------------------------------


class ModScanLog(Base):
    __tablename__ = "mod_scan_log"
    __table_args__ = (
        Index("ix_scan_log_subject", "subject_type", "subject_id", "scanned_at"),
        {"schema": "moderation"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    subject_type: str = Column(SubjectTypeEnum, nullable=False)
    subject_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    idempotency_key: str | None = Column(String(512), nullable=True)
    tool: str = Column(String(100), nullable=False)  # "openai_mod", "rekognition", etc.
    score: float | None = Column(Numeric(5, 4), nullable=True)
    raw_response: dict = Column(JSONB, nullable=False, server_default="{}")
    scanned_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# ActionPropagationLog — append-only audit of each downstream event
# ---------------------------------------------------------------------------


class ActionPropagationLog(Base):
    __tablename__ = "action_propagation_log"
    __table_args__ = (
        Index("ix_prop_log_action", "action_id", "created_at"),
        {"schema": "moderation"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    action_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("moderation.moderation_actions.id"),
        nullable=False,
    )
    target_event: str = Column(String(200), nullable=False)
    target_service: str = Column(String(100), nullable=False)
    status: str = Column(String(50), nullable=False)
    payload: dict = Column(JSONB, nullable=False, server_default="{}")
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# ModConfig — admin-tunable thresholds and weights (replaces FeatureFlag
#             for moderation-internal configuration)
# ---------------------------------------------------------------------------


class ModConfig(Base):
    __tablename__ = "mod_config"
    __table_args__ = (
        UniqueConstraint("key", name="uq_mod_config_key"),
        {"schema": "moderation"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    key: str = Column(String(255), nullable=False)
    value: str = Column(Text, nullable=False)  # JSON-encoded
    description: str | None = Column(Text, nullable=True)
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)
