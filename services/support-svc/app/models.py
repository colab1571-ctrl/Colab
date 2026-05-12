"""
support-svc SQLAlchemy ORM models.

All tables live in the `support` Postgres schema.

Tables:
- support.support_ticket
- support.support_ticket_event
- support.support_csat
- support.kb_article        (pgvector embedding column)
- support.chatbot_session
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func

# pgvector type — stored as TEXT in Alembic migration; pgvector extension handles it.
# Using pgvector's Vector type if available, otherwise fallback to Text for schema
try:
    from pgvector.sqlalchemy import Vector
    _VECTOR_TYPE = Vector(3072)
except ImportError:  # pragma: no cover
    from sqlalchemy import Text as _VectorFallback  # type: ignore[assignment]
    _VECTOR_TYPE = _VectorFallback()  # type: ignore[call-arg]


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# SupportTicket
# ---------------------------------------------------------------------------


class SupportTicket(Base):
    __tablename__ = "support_ticket"
    __table_args__ = (
        Index("idx_st_user_id", "user_id"),
        Index("idx_st_status", "status"),
        Index(
            "idx_st_sla_ack_due",
            "sla_ack_due",
            postgresql_where="first_response_at IS NULL AND status NOT IN ('resolved','closed')",
        ),
        Index(
            "idx_st_sla_resolve_due",
            "sla_resolve_due",
            postgresql_where="resolved_at IS NULL AND status NOT IN ('resolved','closed')",
        ),
        {"schema": "support"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    category: str = Column(
        String(50),
        nullable=False,
    )
    subject: str = Column(String(255), nullable=False)
    body: str = Column(Text, nullable=False)
    status: str = Column(String(30), nullable=False, default="open")
    priority: str = Column(String(20), nullable=False, default="normal")
    tier_at_creation: str = Column(String(20), nullable=False, default="free")

    assigned_to: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)

    sla_ack_due: datetime = Column(DateTime(timezone=True), nullable=False)
    sla_resolve_due: datetime = Column(DateTime(timezone=True), nullable=False)
    sla_paused_seconds: int = Column(Integer, nullable=False, default=0)
    sla_ack_breached_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    sla_resolve_breached_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    sla_paused_at: datetime | None = Column(DateTime(timezone=True), nullable=True)

    first_response_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    resolved_at: datetime | None = Column(DateTime(timezone=True), nullable=True)

    moderation_case_id: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)

    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    events: list[SupportTicketEvent] = relationship(
        "SupportTicketEvent", back_populates="ticket", lazy="selectin", order_by="SupportTicketEvent.created_at"
    )
    csat: SupportCSAT | None = relationship(
        "SupportCSAT", back_populates="ticket", uselist=False, lazy="selectin"
    )


# ---------------------------------------------------------------------------
# SupportTicketEvent
# ---------------------------------------------------------------------------


class SupportTicketEvent(Base):
    __tablename__ = "support_ticket_event"
    __table_args__ = (
        Index("idx_ste_ticket_id", "ticket_id"),
        Index("idx_ste_kind", "ticket_id", "kind"),
        {"schema": "support"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    ticket_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("support.support_ticket.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: str = Column(String(50), nullable=False)
    actor: str = Column(String(20), nullable=False)  # user | agent | system
    actor_id: uuid.UUID | None = Column(UUID(as_uuid=True), nullable=True)
    body: str | None = Column(Text, nullable=True)
    metadata: dict | None = Column(JSONB, nullable=True)

    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    ticket: SupportTicket = relationship("SupportTicket", back_populates="events")


# ---------------------------------------------------------------------------
# SupportCSAT
# ---------------------------------------------------------------------------


class SupportCSAT(Base):
    __tablename__ = "support_csat"
    __table_args__ = (
        UniqueConstraint("ticket_id", name="uq_csat_ticket_id"),
        {"schema": "support"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    ticket_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("support.support_ticket.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    score: int = Column(SmallInteger, nullable=False)
    comment: str | None = Column(Text, nullable=True)

    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    ticket: SupportTicket = relationship("SupportTicket", back_populates="csat")


# ---------------------------------------------------------------------------
# KbArticle (FAQ index with pgvector embedding)
# ---------------------------------------------------------------------------


class KbArticle(Base):
    __tablename__ = "kb_article"
    __table_args__ = (
        Index("idx_kb_tags", "tags", postgresql_using="gin"),
        {"schema": "support"},
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    slug: str = Column(String(255), nullable=False, unique=True)
    title: str = Column(Text, nullable=False)
    body_md: str = Column(Text, nullable=False)
    tags: list[str] = Column(ARRAY(String), nullable=False, server_default="{}")

    # pgvector column — NULL until background embedding worker populates it
    # Declared as Text in migration; pgvector extension handles vector ops
    embedding = Column(_VECTOR_TYPE, nullable=True)

    updated_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# ChatbotSession
# ---------------------------------------------------------------------------


class ChatbotSession(Base):
    __tablename__ = "chatbot_session"
    __table_args__ = {"schema": "support"}

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    ticket_id: uuid.UUID | None = Column(
        UUID(as_uuid=True),
        ForeignKey("support.support_ticket.id"),
        nullable=True,
    )
    turn_count: int = Column(SmallInteger, nullable=False, default=0)
    last_message_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: datetime = Column(DateTime(timezone=True), nullable=False)
