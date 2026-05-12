"""
Tests for the combined-score algorithm and risk-tier routing.

M-090: Unit tests covering:
- All 4 risk tiers (§3 thresholds)
- Forced-human categories
- Dup bump
- Score cap at 1.0
- Worked examples from plan §3.3 and §3.4
- Red-team borderline scenarios from plan §11.1
"""

from __future__ import annotations

import pytest

from app.score import (
    DupResult,
    OpenAIModResult,
    RekognitionResult,
    RoutingDecision,
    combined_score,
    route,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_openai(scores: dict[str, float], flagged_cats: set[str] | None = None) -> OpenAIModResult:
    flagged = flagged_cats if flagged_cats is not None else {k for k, v in scores.items() if v > 0.5}
    return OpenAIModResult(
        flagged=bool(flagged),
        category_scores=scores,
        flagged_categories=flagged,
    )


def make_rek(labels: list[dict]) -> RekognitionResult:
    return RekognitionResult(labels=labels)


NO_DUP = DupResult()
PHASH_DUP = DupResult(phash_match=True)
SEMDUP = DupResult(semdup_match=True)


# ---------------------------------------------------------------------------
# Score algorithm — §3.2 worked examples
# ---------------------------------------------------------------------------


class TestCombinedScore:
    def test_alice_harassment_example(self):
        """Plan §3.3 worked example — should score 1.0."""
        openai = make_openai(
            {"harassment": 0.92, "harassment/threatening": 0.78, "violence": 0.61},
            flagged_cats={"harassment", "harassment/threatening", "violence"},
        )
        rek = make_rek([{"Name": "Violence", "ParentName": "Violence", "Confidence": 82.0}])
        score, breakdown = combined_score(openai, rek, NO_DUP)
        # harassment/threatening * 1.3 = 1.014 → capped → 1.0
        assert score == pytest.approx(1.0, abs=0.001)
        assert breakdown["dup"]["bump_applied"] == 0.0

    def test_bob_allowed_example(self):
        """Plan §3.4 — 'that beat slaps, you're killing it' → score 0.31 → allow."""
        openai = make_openai(
            {"harassment": 0.31, "sexual": 0.02, "violence": 0.04},
            flagged_cats=set(),
        )
        rek = make_rek([])
        score, breakdown = combined_score(openai, rek, NO_DUP)
        assert score < 0.4

    def test_dup_bump_applied(self):
        openai = make_openai({"harassment": 0.25}, flagged_cats=set())
        rek = make_rek([])
        score, breakdown = combined_score(openai, rek, PHASH_DUP)
        # 0.25 + 0.3 = 0.55
        assert score == pytest.approx(0.55, abs=0.01)
        assert breakdown["dup"]["bump_applied"] == pytest.approx(0.3, abs=0.001)

    def test_dup_bump_caps_at_one(self):
        openai = make_openai({"harassment": 0.8}, flagged_cats={"harassment"})
        rek = make_rek([])
        score, _ = combined_score(openai, rek, SEMDUP)
        assert score == pytest.approx(1.0, abs=0.001)

    def test_rekognition_only_image(self):
        openai = make_openai({}, flagged_cats=set())
        rek = make_rek([{"Name": "Explicit Nudity", "ParentName": "Explicit", "Confidence": 70.0}])
        score, breakdown = combined_score(openai, rek, NO_DUP)
        # Rekognition:Explicit weight 1.2 * 0.70 = 0.84
        assert score == pytest.approx(0.84, abs=0.01)

    def test_score_is_never_above_one(self):
        openai = make_openai(
            {k: 0.99 for k in ["harassment", "harassment/threatening", "violence", "sexual"]},
            flagged_cats={"harassment", "harassment/threatening", "violence", "sexual"},
        )
        rek = make_rek([{"Name": "Explicit Nudity", "ParentName": "Explicit", "Confidence": 99.0}])
        score, _ = combined_score(openai, rek, PHASH_DUP)
        assert score == pytest.approx(1.0, abs=0.001)


# ---------------------------------------------------------------------------
# Tier routing — all 4 tiers
# ---------------------------------------------------------------------------


class TestRiskTierRouting:
    def _make_decision(self, score_val: float, cats: set[str] | None = None) -> RoutingDecision:
        openai = make_openai(
            {c: score_val for c in (cats or ["harassment"])},
            flagged_cats=cats or set(),
        )
        rek = make_rek([])
        s, _ = combined_score(openai, rek, NO_DUP)
        return route(s, openai, rek)

    def test_tier_0_below_04(self):
        """Score 0.31 → tier_0_allow, no SLA."""
        openai = make_openai({"harassment": 0.31}, flagged_cats=set())
        rek = make_rek([])
        score, _ = combined_score(openai, rek, NO_DUP)
        decision = route(score, openai, rek)
        assert decision.tier == "tier_0_allow"
        assert decision.action == "allow_log"
        assert decision.sla_hours is None
        assert not decision.forced_human

    def test_tier_0_score_039_no_case(self):
        """Plan §11.1: score=0.39 with harassment category but no threatening → tier_0."""
        openai = make_openai({"harassment": 0.39}, flagged_cats=set())
        rek = make_rek([])
        score, _ = combined_score(openai, rek, NO_DUP)
        decision = route(score, openai, rek)
        assert decision.tier == "tier_0_allow"

    def test_tier_1_boundary_inclusive(self):
        """Plan §11.1: score=0.401 → tier_1_24h."""
        openai = make_openai({"harassment": 0.401}, flagged_cats=set())
        rek = make_rek([])
        score, _ = combined_score(openai, rek, NO_DUP)
        decision = route(score, openai, rek)
        assert decision.tier == "tier_1_24h"
        assert decision.sla_hours == 24

    def test_tier_1_score_05(self):
        openai = make_openai({"harassment": 0.55}, flagged_cats=set())
        rek = make_rek([])
        score, _ = combined_score(openai, rek, NO_DUP)
        decision = route(score, openai, rek)
        assert decision.tier == "tier_1_24h"
        assert decision.action == "soft_warn_user_queue"

    def test_tier_2_score_075(self):
        openai = make_openai({"harassment": 0.75}, flagged_cats={"harassment"})
        rek = make_rek([])
        score, _ = combined_score(openai, rek, NO_DUP)
        decision = route(score, openai, rek)
        assert decision.tier == "tier_2_6h"
        assert decision.action == "hide_content_queue"
        assert decision.sla_hours == 6

    def test_tier_3_score_ge_09(self):
        openai = make_openai({"harassment": 0.95}, flagged_cats={"harassment"})
        rek = make_rek([])
        score, _ = combined_score(openai, rek, NO_DUP)
        decision = route(score, openai, rek)
        assert decision.tier == "tier_3_1h"
        assert decision.action == "auto_hide_temp_mute_queue"
        assert decision.sla_hours == 1


# ---------------------------------------------------------------------------
# Forced-human paths
# ---------------------------------------------------------------------------


class TestForcedHumanRouting:
    def test_csam_always_forced_tier3(self):
        openai = make_openai({"sexual/minors": 0.99}, flagged_cats={"sexual/minors"})
        rek = make_rek([])
        score, _ = combined_score(openai, rek, NO_DUP)
        decision = route(score, openai, rek)
        assert decision.forced_human is True
        assert decision.is_csam is True
        assert decision.forced_reason == "csam_path"
        assert decision.tier == "tier_3_1h"

    def test_harassment_threatening_forced(self):
        openai = make_openai(
            {"harassment/threatening": 0.78, "harassment": 0.9},
            flagged_cats={"harassment/threatening", "harassment"},
        )
        rek = make_rek([])
        score, _ = combined_score(openai, rek, NO_DUP)
        decision = route(score, openai, rek)
        assert decision.forced_human is True
        assert "harassment/threatening" in decision.forced_reason

    def test_violence_graphic_forced(self):
        openai = make_openai({"violence/graphic": 0.8}, flagged_cats={"violence/graphic"})
        rek = make_rek([])
        score, _ = combined_score(openai, rek, NO_DUP)
        decision = route(score, openai, rek)
        assert decision.forced_human is True

    def test_rekognition_hate_symbols_forced(self):
        openai = make_openai({"harassment": 0.2}, flagged_cats=set())
        rek = make_rek([{"Name": "Nazi Symbol", "ParentName": "Hate Symbols", "Confidence": 90.0}])
        score, _ = combined_score(openai, rek, NO_DUP)
        decision = route(score, openai, rek)
        assert decision.forced_human is True
        assert "Hate Symbols" in decision.forced_reason

    def test_ip_claim_forced(self):
        openai = make_openai({"harassment": 0.2}, flagged_cats=set())
        rek = make_rek([])
        score, _ = combined_score(openai, rek, NO_DUP)
        decision = route(score, openai, rek, has_ip_claim=True)
        assert decision.forced_human is True
        assert decision.forced_reason == "ip_claim"

    def test_forced_human_at_low_score_still_at_least_tier1(self):
        """Plan §7.3: forced_human cases at score<0.4 get bumped to at least tier_1."""
        openai = make_openai({"harassment/threatening": 0.15}, flagged_cats={"harassment/threatening"})
        rek = make_rek([])
        score, _ = combined_score(openai, rek, NO_DUP)
        # score = 1.3 * 0.15 = 0.195 < 0.4, but forced_human → at least tier_1
        decision = route(score, openai, rek)
        assert decision.forced_human is True
        assert decision.tier != "tier_0_allow"

    def test_multimodal_evasion_plan_117(self):
        """
        Plan §11.7: text 'you know what to do' scores 0.2; image Violence 0.7.
        Combined must route to tier_2 (image bias, not text bias).
        """
        openai = make_openai({"harassment": 0.2}, flagged_cats=set())
        rek = make_rek([{"Name": "Violence", "ParentName": "Violence", "Confidence": 70.0}])
        score, _ = combined_score(openai, rek, NO_DUP)
        decision = route(score, openai, rek)
        assert decision.tier == "tier_2_6h"
        assert "allow" not in decision.action
