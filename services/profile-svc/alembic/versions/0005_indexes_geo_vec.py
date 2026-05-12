"""0005 — additional partial indexes for discovery and review.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Partial index for free-tier discovery feed: badge_granted + visible to non-premium
    op.execute(
        "CREATE INDEX ix_profiles_discovery ON profiles(badge_state, is_visible_to_non_premium) "
        "WHERE badge_state = 'badge_granted' AND is_visible_to_non_premium = true"
    )
    # Partial index: only passed portfolio items served publicly
    op.execute(
        "CREATE INDEX ix_portfolio_passed ON portfolio_items(profile_id) "
        "WHERE ai_review_status = 'passed'"
    )
    # Trigram index on location_city for autocomplete
    op.execute("CREATE INDEX ix_profiles_city_trgm ON profiles USING gin(location_city gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_profiles_discovery")
    op.execute("DROP INDEX IF EXISTS ix_portfolio_passed")
    op.execute("DROP INDEX IF EXISTS ix_profiles_city_trgm")
