"""
moderation-svc — Combined score algorithm and risk-tier routing.

Implements plan §3 verbatim:
- Weighted per-category max from each tool
- Dup bump (+0.3)
- 1.0 cap
- Tier routing: <0.4 allow / 0.4-0.7 tier_1_24h / 0.7-0.9 tier_2_6h / >=0.9 tier_3_1h
- Forced-human paths for CSAM / harassment-threat / hate-symbol / IP claims
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

from app.config import (
    ALWAYS_HUMAN_OPENAI,
    ALWAYS_HUMAN_REKOGNITION,
    DEFAULT_CATEGORY_WEIGHTS,
    get_mod_settings,
)


# ---------------------------------------------------------------------------
# Raw scan results from each tool
# ---------------------------------------------------------------------------


@dataclass
class OpenAIModResult:
    """Normalised output from OpenAI omni-moderation-latest."""

    flagged: bool = False
    category_scores: dict[str, float] = field(default_factory=dict)
    flagged_categories: set[str] = field(default_factory=set)
    raw: dict = field(default_factory=dict)

    @property
    def max_score(self) -> float:
        return max(self.category_scores.values(), default=0.0)


@dataclass
class RekognitionResult:
    """Normalised output from AWS Rekognition DetectModerationLabels."""

    labels: list[dict] = field(default_factory=list)  # [{name, parent, confidence}]
    raw: dict = field(default_factory=dict)

    def parent_scores(self) -> dict[str, float]:
        """Return max confidence per parent label (normalized 0-1)."""
        scores: dict[str, float] = {}
        for label in self.labels:
            parent = label.get("ParentName") or label.get("Name", "")
            conf = label.get("Confidence", 0.0) / 100.0
            scores[parent] = max(scores.get(parent, 0.0), conf)
        return scores


@dataclass
class DupResult:
    """Deduplication signals from pHash / Chromaprint / pgvector."""

    phash_match: bool = False
    chromaprint_match: bool = False
    semdup_match: bool = False

    @property
    def any_match(self) -> bool:
        return self.phash_match or self.chromaprint_match or self.semdup_match


# ---------------------------------------------------------------------------
# Routing decision
# ---------------------------------------------------------------------------


class RoutingDecision(NamedTuple):
    action: str  # "allow_log" | "soft_warn_user_queue" | "hide_content_queue" | "auto_hide_temp_mute_queue"
    tier: str  # "tier_0_allow" | "tier_1_24h" | "tier_2_6h" | "tier_3_1h"
    sla_hours: int | None  # None = no SLA
    forced_human: bool
    forced_reason: str | None
    is_csam: bool
    score: float


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def combined_score(
    openai: OpenAIModResult,
    rekognition: RekognitionResult,
    dup: DupResult,
    weights: dict[str, float] | None = None,
) -> tuple[float, dict]:
    """
    Compute the combined score per plan §3.2.

    Returns (score, breakdown_dict).
    """
    if weights is None:
        weights = DEFAULT_CATEGORY_WEIGHTS

    # --- text weighted max ---
    text_weighted = 0.0
    for cat, raw_score in openai.category_scores.items():
        w = weights.get(cat, 1.0)
        text_weighted = max(text_weighted, w * raw_score)
    # also consider the bare flagged score as a floor
    text_weighted = max(text_weighted, openai.max_score)

    # --- image weighted max ---
    r_scores = rekognition.parent_scores()
    image_weighted = 0.0
    for cat, conf in r_scores.items():
        w = weights.get(f"Rekognition:{cat}", weights.get(cat, 1.0))
        image_weighted = max(image_weighted, w * conf)

    # --- dup bump ---
    settings = get_mod_settings()
    dup_bump = settings.dup_bump if dup.any_match else 0.0

    # --- combine ---
    raw = max(text_weighted, image_weighted)
    score = min(1.0, raw + dup_bump)

    breakdown = {
        "openai": {
            "max_score": openai.max_score,
            "weighted": round(text_weighted, 4),
            "flagged_categories": list(openai.flagged_categories),
            "category_scores": {k: round(v, 4) for k, v in openai.category_scores.items()},
        },
        "rekognition": {
            "parent_scores": {k: round(v, 4) for k, v in r_scores.items()},
            "weighted": round(image_weighted, 4),
        },
        "dup": {
            "phash_match": dup.phash_match,
            "chromaprint_match": dup.chromaprint_match,
            "semdup_match": dup.semdup_match,
            "bump_applied": round(dup_bump, 4),
        },
        "weighted": round(score, 4),
    }
    return score, breakdown


def route(
    score: float,
    openai: OpenAIModResult,
    rekognition: RekognitionResult,
    *,
    has_ip_claim: bool = False,
) -> RoutingDecision:
    """
    Map combined score + category signals to a routing decision.

    Forced-human paths take precedence over threshold routing per plan §3.2.
    """
    settings = get_mod_settings()
    r_parent_names = {label.get("ParentName") or label.get("Name", "") for label in rekognition.labels}

    # --- CSAM — hardest path ---
    if "sexual/minors" in openai.flagged_categories:
        return RoutingDecision(
            action="auto_hide_temp_mute_queue",
            tier="tier_3_1h",
            sla_hours=settings.tier3_sla_hours,
            forced_human=True,
            forced_reason="csam_path",
            is_csam=True,
            score=score,
        )

    # --- Forced-human but score-informed tier ---
    forced = False
    forced_reason: str | None = None

    if "harassment/threatening" in openai.flagged_categories:
        forced, forced_reason = True, "harassment/threatening"
    elif "violence/graphic" in openai.flagged_categories:
        forced, forced_reason = True, "violence/graphic"
    elif ALWAYS_HUMAN_REKOGNITION.intersection(r_parent_names):
        matched = ALWAYS_HUMAN_REKOGNITION.intersection(r_parent_names)
        forced, forced_reason = True, f"rekognition:{','.join(matched)}"
    elif has_ip_claim:
        forced, forced_reason = True, "ip_claim"

    # --- Threshold routing ---
    if score < settings.tier1_threshold:
        action = "allow_log"
        tier = "tier_0_allow"
        sla = None
    elif score < settings.tier2_threshold:
        action = "soft_warn_user_queue"
        tier = "tier_1_24h"
        sla = settings.tier1_sla_hours
    elif score < settings.tier3_threshold:
        action = "hide_content_queue"
        tier = "tier_2_6h"
        sla = settings.tier2_sla_hours
    else:
        action = "auto_hide_temp_mute_queue"
        tier = "tier_3_1h"
        sla = settings.tier3_sla_hours

    # Forced-human cases get at least tier_2
    if forced and tier == "tier_0_allow":
        action = "soft_warn_user_queue"
        tier = "tier_1_24h"
        sla = settings.tier1_sla_hours

    return RoutingDecision(
        action=action,
        tier=tier,
        sla_hours=sla,
        forced_human=forced,
        forced_reason=forced_reason,
        is_csam=False,
        score=score,
    )
