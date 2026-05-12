"""
matching-svc — ranking formula implementation.

Formula (plan §3.1):
  score = 0.40 × emb_sim
        + 0.25 × comp_voc
        + 0.15 × activity
        + 0.10 × health
        + 0.10 × rand

All terms normalized to [0.0, 1.0].

Worked example from plan §3.3:
  A→B: emb_sim=0.82, comp_voc=0.95, activity=0.86, health=0.75, rand=0.52
  score_B = 0.328 + 0.238 + 0.129 + 0.075 + 0.052 = 0.822

  A→C: emb_sim=0.71, comp_voc=0.50, activity=0.105, health=0.40, rand=0.48
  score_C = 0.284 + 0.125 + 0.016 + 0.040 + 0.048 = 0.513
"""

from __future__ import annotations

import hashlib
import math
import random
import struct
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Affinity matrix (9×9) — seed values per plan §4.2
# ---------------------------------------------------------------------------

VOCATION_CATEGORIES = [
    "Visual Arts",
    "Performing Arts",
    "Literary Arts",
    "Music",
    "Film/Video",
    "Design",
    "Digital/Tech",
    "Media & Journalism",
    "Craft & Maker",
]

# Seed affinity matrix — admin-editable via VocationAffinity table
AFFINITY_SEED: dict[str, dict[str, float]] = {
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


@dataclass
class RankingWeights:
    weight_emb_sim: float = 0.40
    weight_comp_voc: float = 0.25
    weight_activity: float = 0.15
    weight_health: float = 0.10
    weight_rand: float = 0.10
    activity_lambda: float = 0.05


def comp_voc_score(
    viewer_vocations: list[str],
    candidate_vocations: list[str],
    matrix: dict[str, dict[str, float]] | None = None,
) -> float:
    """
    Max affinity across all viewer × candidate vocation pairs.
    Multi-vocation: rewards cross-disciplinary candidates.
    """
    if matrix is None:
        matrix = AFFINITY_SEED
    if not viewer_vocations or not candidate_vocations:
        return 0.50  # default to moderate if vocations unknown

    scores = []
    for v in viewer_vocations:
        row = matrix.get(v, {})
        for c in candidate_vocations:
            scores.append(row.get(c, 0.50))
    return max(scores) if scores else 0.50


def activity_score(last_active_at: datetime | None, lambda_: float = 0.05) -> float:
    """
    Exponential decay: activity = exp(-λ × days_since_active)
    λ = 0.05 → half-life ~14 days.
    Never active → 0.0.
    """
    if last_active_at is None:
        return 0.0
    now = datetime.now(tz=timezone.utc)
    if last_active_at.tzinfo is None:
        last_active_at = last_active_at.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - last_active_at).total_seconds() / 86_400)
    return max(0.0, min(1.0, math.exp(-lambda_ * days)))


def rand_component(viewer_id: str, candidate_id: str, day: date | None = None) -> float:
    """
    Deterministic Gaussian noise per (viewer, candidate, day).
    Seed = SHA-256(viewer_id:candidate_id:YYYY-MM-DD).
    Stable within a day; different across days → prevents filter-bubble lock-in.
    """
    if day is None:
        day = date.today()
    seed_bytes = hashlib.sha256(
        f"{viewer_id}:{candidate_id}:{day.isoformat()}".encode()
    ).digest()
    seed_int = struct.unpack("<Q", seed_bytes[:8])[0]
    val = random.Random(seed_int).gauss(0.5, 0.15)
    return max(0.0, min(1.0, val))


def compute_score(
    viewer_id: str,
    candidate_id: str,
    emb_sim: float,
    comp_voc: float,
    last_active_at: datetime | None,
    health: float,
    weights: RankingWeights | None = None,
    day: date | None = None,
) -> tuple[float, float, float, float, float]:
    """
    Compute weighted match score.

    Returns (total_score, emb_sim, comp_voc_score, activity_score, rand_score).

    Cold-start handling: if emb_sim == 0.0 (no embedding), redistribute weight:
      score = 0.45×comp_voc + 0.25×activity + 0.20×health + 0.10×rand
    """
    if weights is None:
        weights = RankingWeights()

    act = activity_score(last_active_at, weights.activity_lambda)
    rnd = rand_component(viewer_id, candidate_id, day)

    # Clamp all inputs to [0, 1]
    emb_sim = max(0.0, min(1.0, emb_sim))
    comp_voc = max(0.0, min(1.0, comp_voc))
    health = max(0.0, min(1.0, health))

    if emb_sim == 0.0:
        # Cold-start formula (no embedding available)
        total = 0.45 * comp_voc + 0.25 * act + 0.20 * health + 0.10 * rnd
    else:
        total = (
            weights.weight_emb_sim * emb_sim
            + weights.weight_comp_voc * comp_voc
            + weights.weight_activity * act
            + weights.weight_health * health
            + weights.weight_rand * rnd
        )

    return max(0.0, min(1.0, total)), emb_sim, comp_voc, act, rnd
