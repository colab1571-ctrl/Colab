"""0004 — profile_vocations, profile_skills, portfolio_items, external_links, personality_answers, profile_reviews.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, JSONB, UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # profile_vocations
    op.create_table(
        "profile_vocations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("profile_id", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("subtag", sa.String(128), nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("flagged_for_review", sa.Boolean, nullable=False, server_default="false"),
        sa.UniqueConstraint("profile_id", "category", name="uq_vocations_profile_category"),
    )
    op.create_index("ix_vocations_subtag", "profile_vocations", ["subtag"])
    # Partial unique: only one primary vocation per profile
    op.execute(
        "CREATE UNIQUE INDEX uix_vocations_primary ON profile_vocations(profile_id) WHERE is_primary = true"
    )

    # profile_skills
    op.create_table(
        "profile_skills",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("profile_id", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label_raw", sa.String(40), nullable=False),
        sa.Column("label_lower", sa.String(40), nullable=False),
        sa.Column("label_normalized", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("profile_id", "label_lower", name="uq_skills_profile_label"),
    )

    # portfolio_items
    op.create_table(
        "portfolio_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("profile_id", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.SmallInteger, nullable=False),
        sa.Column("type", sa.String(8), nullable=False),
        sa.Column("s3_bucket", sa.String(255), nullable=False, server_default="''"),
        sa.Column("s3_key", sa.String(1024), nullable=False, server_default="''"),
        sa.Column("mime", sa.String(128), nullable=False, server_default="''"),
        sa.Column("size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("caption", sa.String(200), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("phash", sa.BigInteger, nullable=True),
        sa.Column("ahash", sa.BigInteger, nullable=True),
        sa.Column("chromaprint_fp", sa.Text, nullable=True),
        sa.Column("ai_review_status", sa.String(16), nullable=False, server_default="'pending'"),
        sa.Column("ai_review_score", sa.Float, nullable=True),
        sa.Column("ai_review_payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("position >= 0 AND position <= 11", name="ck_portfolio_position"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_portfolio_size"),
        sa.CheckConstraint("type IN ('image','audio','video','link')", name="ck_portfolio_type"),
        sa.CheckConstraint("ai_review_status IN ('pending','passed','flagged','hidden')", name="ck_portfolio_ai_status"),
        sa.UniqueConstraint("profile_id", "position", name="uq_portfolio_profile_position"),
    )
    op.create_index("ix_portfolio_profile_id", "portfolio_items", ["profile_id"])
    # pgvector embedding on portfolio items
    op.execute("ALTER TABLE portfolio_items ADD COLUMN embedding vector(1536)")
    op.execute("CREATE INDEX ix_portfolio_embedding_hnsw ON portfolio_items USING hnsw(embedding vector_cosine_ops) WITH (m=16, ef_construction=64)")

    # external_links
    op.create_table(
        "external_links",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("profile_id", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("provider_handle", sa.String(255), nullable=True),
        sa.Column("provider_id", sa.String(255), nullable=True),
        sa.Column("encrypted_access_token", BYTEA, nullable=True),
        sa.Column("encrypted_refresh_token", BYTEA, nullable=True),
        sa.Column("data_key_ciphertext", BYTEA, nullable=True),
        sa.Column("scopes", ARRAY(sa.String), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_state", sa.String(16), nullable=False, server_default="'ok'"),
        sa.CheckConstraint("provider IN ('instagram','youtube','spotify')", name="ck_external_provider"),
        sa.CheckConstraint("sync_state IN ('ok','needs_reauth','revoked')", name="ck_external_sync_state"),
        sa.UniqueConstraint("profile_id", "provider", name="uq_external_profile_provider"),
    )
    op.create_index("ix_external_profile_id", "external_links", ["profile_id"])

    # personality_answers
    op.create_table(
        "personality_answers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("profile_id", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_key", sa.String(64), nullable=False),
        sa.Column("answer_key", sa.String(64), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("profile_id", "question_key", name="uq_personality_profile_question"),
    )

    # profile_reviews
    op.create_table(
        "profile_reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("profile_id", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_kind", sa.String(32), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("reasons", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("provider_versions", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('text','image','video','audio')", name="ck_review_kind"),
        sa.CheckConstraint("target_kind IN ('profile_text','portfolio_item','display_name','bio')", name="ck_review_target_kind"),
        sa.CheckConstraint("status IN ('passed','flagged','escalated','overridden')", name="ck_review_status"),
        sa.CheckConstraint("score >= 0 AND score <= 1", name="ck_review_score"),
    )
    op.create_index("ix_reviews_profile_created", "profile_reviews", ["profile_id", "created_at"])


def downgrade() -> None:
    op.drop_table("profile_reviews")
    op.drop_table("personality_answers")
    op.drop_table("external_links")
    op.execute("DROP INDEX IF EXISTS ix_portfolio_embedding_hnsw")
    op.drop_table("portfolio_items")
    op.drop_table("profile_skills")
    op.execute("DROP INDEX IF EXISTS uix_vocations_primary")
    op.drop_table("profile_vocations")
