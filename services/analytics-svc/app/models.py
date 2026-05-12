"""
analytics-svc SQLAlchemy ORM models.

Tables in `analytics` schema:
- Event: raw event mirror (append-only insert from ingestion proxy)
- KPIRollup: nightly rollup output
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Event(Base):
    """
    Raw event mirror from the ingestion proxy.

    Each event forwarded to PostHog is also written here for offline KPI computation.
    This table is effectively append-only (no UPDATE/DELETE in application code).
    """

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_ts", "ts"),
        Index("ix_events_user_ts", "user_id", "ts"),
        Index("ix_events_event_ts", "event", "ts"),
        {"schema": "analytics"},
    )

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    event = Column(String(128), nullable=False)
    ts = Column(DateTime(timezone=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    session_id = Column(String(128), nullable=True)
    props = Column(JSONB, nullable=True)
    received_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KPIRollup(Base):
    """
    Nightly KPI rollup output.

    Composite PK on (day, key, dims) — ON CONFLICT DO UPDATE for idempotent backfill.
    """

    __tablename__ = "kpi_rollup"
    __table_args__ = (
        UniqueConstraint("day", "key", "dims", name="uq_kpi_rollup_day_key_dims"),
        Index("ix_kpi_rollup_key_day", "key", "day"),
        {"schema": "analytics"},
    )

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    day = Column(DateTime(timezone=True), nullable=False)  # date stored as timestamptz midnight UTC
    key = Column(String(64), nullable=False)
    dims = Column(JSONB, nullable=False, default=dict)
    value = Column(Numeric, nullable=True)
    count_n = Column(BigInteger, nullable=True)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
