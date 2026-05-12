"""
matching-svc — ORM models.

Tables (all in `matching` schema):
  match_scores, recommendation_sets, ranking_weight_config, vocation_affinity
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class MatchScore(Base):
    """Pre-computed pair-wise match score. Nightly rerank + on-demand."""

    __tablename__ = "match_scores"
    __table_args__ = (
        Index("ix_match_scores_from_score", "from_profile_id", "score"),
        Index("ix_match_scores_computed_at", "computed_at"),
        {"schema": "matching"},
    )

    from_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    to_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    emb_sim: Mapped[float | None] = mapped_column(Float, nullable=True)
    comp_voc: Mapped[float | None] = mapped_column(Float, nullable=True)
    activity: Mapped[float | None] = mapped_column(Float, nullable=True)
    health: Mapped[float | None] = mapped_column(Float, nullable=True)
    rand_component: Mapped[float | None] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class RecommendationSet(Base):
    """Daily 'Picked for you' recommendation set per user."""

    __tablename__ = "recommendation_sets"
    __table_args__ = ({"schema": "matching"},)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    profile_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    rationale: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class RankingWeightConfig(Base):
    """Admin-editable ranking weights (singleton; constraint enforces sum=1)."""

    __tablename__ = "ranking_weight_config"
    __table_args__ = (
        CheckConstraint(
            "abs(weight_emb_sim + weight_comp_voc + weight_activity + weight_health + weight_rand - 1.0) < 0.001",
            name="ck_weights_sum_to_one",
        ),
        {"schema": "matching"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    weight_emb_sim: Mapped[float] = mapped_column(Float, nullable=False, default=0.40)
    weight_comp_voc: Mapped[float] = mapped_column(Float, nullable=False, default=0.25)
    weight_activity: Mapped[float] = mapped_column(Float, nullable=False, default=0.15)
    weight_health: Mapped[float] = mapped_column(Float, nullable=False, default=0.10)
    weight_rand: Mapped[float] = mapped_column(Float, nullable=False, default=0.10)
    activity_lambda: Mapped[float] = mapped_column(Float, nullable=False, default=0.05)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class VocationAffinity(Base):
    """9×9 affinity matrix — singleton JSONB row."""

    __tablename__ = "vocation_affinity"
    __table_args__ = ({"schema": "matching"},)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    matrix: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
