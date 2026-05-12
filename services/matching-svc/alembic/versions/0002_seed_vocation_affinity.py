"""0002 — seed vocation_affinity table with 9×9 affinity matrix.

Populates the singleton `matching.vocation_affinity` row with the editorial
affinity matrix from plan §4.2. Admin-editable via admin-svc after initial
seeding; changes take effect on next nightly rerank.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-11
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# 9×9 affinity matrix (plan §4.2)
# Diagonal = 0.50 (same-category: fine but not hero case)
# Film/Video ↔ Music = 0.95 (canonical collab)
# Design ↔ Digital/Tech = 0.90
# ---------------------------------------------------------------------------

AFFINITY_MATRIX: dict[str, dict[str, float]] = {
    "Visual Arts": {
        "Visual Arts": 0.50, "Performing Arts": 0.60, "Literary Arts": 0.65,
        "Music": 0.55, "Film/Video": 0.80, "Design": 0.85,
        "Digital/Tech": 0.75, "Media & Journalism": 0.70, "Craft & Maker": 0.70,
    },
    "Performing Arts": {
        "Visual Arts": 0.60, "Performing Arts": 0.50, "Literary Arts": 0.70,
        "Music": 0.80, "Film/Video": 0.85, "Design": 0.45,
        "Digital/Tech": 0.55, "Media & Journalism": 0.80, "Craft & Maker": 0.35,
    },
    "Literary Arts": {
        "Visual Arts": 0.65, "Performing Arts": 0.70, "Literary Arts": 0.50,
        "Music": 0.75, "Film/Video": 0.80, "Design": 0.55,
        "Digital/Tech": 0.50, "Media & Journalism": 0.85, "Craft & Maker": 0.40,
    },
    "Music": {
        "Visual Arts": 0.55, "Performing Arts": 0.80, "Literary Arts": 0.75,
        "Music": 0.50, "Film/Video": 0.95, "Design": 0.45,
        "Digital/Tech": 0.65, "Media & Journalism": 0.70, "Craft & Maker": 0.35,
    },
    "Film/Video": {
        "Visual Arts": 0.80, "Performing Arts": 0.85, "Literary Arts": 0.80,
        "Music": 0.95, "Film/Video": 0.50, "Design": 0.60,
        "Digital/Tech": 0.75, "Media & Journalism": 0.80, "Craft & Maker": 0.40,
    },
    "Design": {
        "Visual Arts": 0.85, "Performing Arts": 0.45, "Literary Arts": 0.55,
        "Music": 0.45, "Film/Video": 0.60, "Design": 0.50,
        "Digital/Tech": 0.90, "Media & Journalism": 0.55, "Craft & Maker": 0.75,
    },
    "Digital/Tech": {
        "Visual Arts": 0.75, "Performing Arts": 0.55, "Literary Arts": 0.50,
        "Music": 0.65, "Film/Video": 0.75, "Design": 0.90,
        "Digital/Tech": 0.50, "Media & Journalism": 0.65, "Craft & Maker": 0.50,
    },
    "Media & Journalism": {
        "Visual Arts": 0.70, "Performing Arts": 0.80, "Literary Arts": 0.85,
        "Music": 0.70, "Film/Video": 0.80, "Design": 0.55,
        "Digital/Tech": 0.65, "Media & Journalism": 0.50, "Craft & Maker": 0.40,
    },
    "Craft & Maker": {
        "Visual Arts": 0.70, "Performing Arts": 0.35, "Literary Arts": 0.40,
        "Music": 0.35, "Film/Video": 0.40, "Design": 0.75,
        "Digital/Tech": 0.50, "Media & Journalism": 0.40, "Craft & Maker": 0.50,
    },
}


def upgrade() -> None:
    # Upsert singleton row (safe to re-run; conflict on unique partial index)
    op.execute(
        sa.text(
            """
            INSERT INTO matching.vocation_affinity (matrix)
            VALUES (:matrix)
            ON CONFLICT ((true)) DO UPDATE
              SET matrix = EXCLUDED.matrix,
                  updated_at = now()
            """
        ).bindparams(matrix=json.dumps(AFFINITY_MATRIX))
    )

    # Seed default ranking weight config if not already present
    op.execute(
        sa.text(
            """
            INSERT INTO matching.ranking_weight_config
              (weight_emb_sim, weight_comp_voc, weight_activity, weight_health, weight_rand, activity_lambda)
            VALUES (0.40, 0.25, 0.15, 0.10, 0.10, 0.05)
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute("DELETE FROM matching.vocation_affinity")
    op.execute("DELETE FROM matching.ranking_weight_config")
