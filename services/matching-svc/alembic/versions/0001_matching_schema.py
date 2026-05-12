"""0001 — create matching schema + match_scores, recommendation_sets,
ranking_weight_config, vocation_affinity tables.

Revision ID: 0001
Revises:
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create matching schema
    op.execute("CREATE SCHEMA IF NOT EXISTS matching")

    # match_scores
    op.create_table(
        "match_scores",
        sa.Column("from_profile_id", UUID(as_uuid=True), nullable=False),
        sa.Column("to_profile_id", UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("emb_sim", sa.Float, nullable=True),
        sa.Column("comp_voc", sa.Float, nullable=True),
        sa.Column("activity", sa.Float, nullable=True),
        sa.Column("health", sa.Float, nullable=True),
        sa.Column("rand_component", sa.Float, nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("from_profile_id", "to_profile_id"),
        schema="matching",
    )
    op.create_index(
        "ix_match_scores_from_score",
        "match_scores",
        ["from_profile_id", "score"],
        schema="matching",
    )
    op.create_index(
        "ix_match_scores_computed_at",
        "match_scores",
        ["computed_at"],
        schema="matching",
    )

    # recommendation_sets
    op.create_table(
        "recommendation_sets",
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("profile_ids", ARRAY(UUID(as_uuid=True)), nullable=False),
        sa.Column("rationale", JSONB, nullable=False, server_default="'{}'"),
        schema="matching",
    )

    # ranking_weight_config
    op.create_table(
        "ranking_weight_config",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("weight_emb_sim", sa.Float, nullable=False, server_default="0.40"),
        sa.Column("weight_comp_voc", sa.Float, nullable=False, server_default="0.25"),
        sa.Column("weight_activity", sa.Float, nullable=False, server_default="0.15"),
        sa.Column("weight_health", sa.Float, nullable=False, server_default="0.10"),
        sa.Column("weight_rand", sa.Float, nullable=False, server_default="0.10"),
        sa.Column("activity_lambda", sa.Float, nullable=False, server_default="0.05"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "abs(weight_emb_sim + weight_comp_voc + weight_activity + weight_health + weight_rand - 1.0) < 0.001",
            name="ck_weights_sum_to_one",
        ),
        schema="matching",
    )

    # vocation_affinity — singleton JSONB matrix
    op.create_table(
        "vocation_affinity",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("matrix", JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
        schema="matching",
    )
    # Singleton enforcement: unique partial index on true
    op.execute(
        "CREATE UNIQUE INDEX uix_vocation_affinity_singleton "
        "ON matching.vocation_affinity ((true))"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS matching.vocation_affinity CASCADE")
    op.execute("DROP TABLE IF EXISTS matching.ranking_weight_config CASCADE")
    op.execute("DROP TABLE IF EXISTS matching.recommendation_sets CASCADE")
    op.execute("DROP TABLE IF EXISTS matching.match_scores CASCADE")
    op.execute("DROP SCHEMA IF EXISTS matching CASCADE")
