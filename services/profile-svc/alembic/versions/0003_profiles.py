"""0003 — profiles base table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(40), nullable=True, unique=True),
        sa.Column("bio", sa.Text, nullable=True),
        sa.Column("obsessed_with", sa.Text, nullable=True),
        sa.Column("looking_for", sa.Text, nullable=True),
        sa.Column("past_experience", sa.Text, nullable=True),
        # PostGIS geography column — created via raw SQL
        sa.Column("location_city", sa.String(120), nullable=True),
        sa.Column("location_country", sa.String(2), nullable=True),
        sa.Column("radius_value", sa.Integer, nullable=False, server_default="50"),
        sa.Column("radius_unit", sa.String(2), nullable=False, server_default="'mi'"),
        sa.Column("open_to_remote", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("experience_level", sa.SmallInteger, nullable=True),
        sa.Column("personality_archetype", sa.String(32), nullable=True),
        sa.Column("profile_health_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("badge_state", sa.String(32), nullable=False, server_default="'unverified'"),
        sa.Column("badge_granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("badge_held_reason", sa.String(64), nullable=True),
        sa.Column("is_visible_to_non_premium", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("char_length(bio) <= 280", name="ck_profiles_bio_len"),
        sa.CheckConstraint("char_length(obsessed_with) <= 140", name="ck_profiles_obsessed_len"),
        sa.CheckConstraint("radius_value >= 1 AND radius_value <= 9999", name="ck_profiles_radius"),
        sa.CheckConstraint("experience_level >= 1 AND experience_level <= 5", name="ck_profiles_exp"),
        sa.CheckConstraint("profile_health_score >= 0 AND profile_health_score <= 100", name="ck_profiles_health"),
        sa.CheckConstraint(
            "badge_state IN ('unverified','email_verified','identity_pending','identity_approved','ai_review_pending','badge_granted','badge_held','badge_revoked')",
            name="ck_profiles_badge_state",
        ),
        sa.CheckConstraint("radius_unit IN ('mi','km')", name="ck_profiles_radius_unit"),
        sa.UniqueConstraint("user_id", name="uq_profiles_user_id"),
    )

    # PostGIS geography column — must use raw DDL
    op.execute("ALTER TABLE profiles ADD COLUMN location_point geography(Point,4326)")
    # GiST index for PostGIS
    op.execute("CREATE INDEX ix_profiles_location_gist ON profiles USING gist(location_point)")

    # pgvector embedding column
    op.execute("ALTER TABLE profiles ADD COLUMN embedding vector(1536)")
    # HNSW index (supports 1536d; ivfflat capped at 2000d but HNSW is preferred)
    op.execute("CREATE INDEX ix_profiles_embedding_hnsw ON profiles USING hnsw(embedding vector_cosine_ops) WITH (m=16, ef_construction=64)")

    # Standard indexes
    op.create_index("ix_profiles_badge_state", "profiles", ["badge_state"])
    op.create_index("ix_profiles_health_desc", "profiles", ["profile_health_score"], postgresql_ops={"profile_health_score": "DESC"})
    op.create_index("ix_profiles_last_active", "profiles", ["last_active_at"], postgresql_ops={"last_active_at": "DESC"})

    # updated_at trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION profiles_set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.updated_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_profiles_updated_at
        BEFORE UPDATE ON profiles
        FOR EACH ROW EXECUTE FUNCTION profiles_set_updated_at()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_profiles_updated_at ON profiles")
    op.execute("DROP FUNCTION IF EXISTS profiles_set_updated_at()")
    op.drop_table("profiles")
