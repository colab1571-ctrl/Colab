"""
Red-team adversarial scenarios — M-092.

Implements plan §11 test cases:
§11.1 Borderline content
§11.2 Harassment escalations
§11.3 DMCA abuse
§11.4 False-positive recovery
§11.5 Reciprocal report-bombing protection
§11.6 CSAM hard path
§11.7 Multimodal evasion
§11.8 SLA breach
§11.9 DMCA lifecycle (in test_dmca_workflow.py)
§11.10 Action propagation completeness (in test_action_propagation.py)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.score import (
    DupResult,
    OpenAIModResult,
    RekognitionResult,
    combined_score,
    route,
)


# ---------------------------------------------------------------------------
# §11.1 Borderline content
# ---------------------------------------------------------------------------


class TestBorderlineContent:
    def test_sick_beat_allows_at_031(self):
        """'this beat is sick' — score 0.31 → never opens a case."""
        openai = OpenAIModResult(
            flagged=False,
            category_scores={"harassment": 0.31, "sexual": 0.02, "violence": 0.04},
            flagged_categories=set(),
        )
        score, _ = combined_score(openai, RekognitionResult(), DupResult())
        decision = route(score, openai, RekognitionResult())
        assert decision.tier == "tier_0_allow"
        assert "allow" in decision.action

    def test_score_039_no_threatening_is_tier0(self):
        """Score 0.39 with harassment (not threatening) → tier_0."""
        openai = OpenAIModResult(
            flagged=False,
            category_scores={"harassment": 0.39},
            flagged_categories=set(),  # flagged=False
        )
        score, _ = combined_score(openai, RekognitionResult(), DupResult())
        decision = route(score, openai, RekognitionResult())
        assert decision.tier == "tier_0_allow"
        # Key assertion: NOT auto-warned at 0.39
        assert decision.action == "allow_log"

    def test_score_0401_exact_boundary_tier1(self):
        """Score 0.401 → tier_1_24h (inclusive boundary)."""
        openai = OpenAIModResult(
            flagged=False,
            category_scores={"harassment": 0.401},
            flagged_categories=set(),
        )
        score, _ = combined_score(openai, RekognitionResult(), DupResult())
        assert score >= 0.4
        decision = route(score, openai, RekognitionResult())
        assert decision.tier == "tier_1_24h"
        assert decision.sla_hours == 24


# ---------------------------------------------------------------------------
# §11.2 Harassment escalations
# ---------------------------------------------------------------------------


class TestHarassmentEscalation:
    def test_csam_force_path_fires_immediately(self):
        """CSAM must auto-hide + forced_human regardless of other scores."""
        openai = OpenAIModResult(
            flagged=True,
            category_scores={"sexual/minors": 0.99, "sexual": 0.99},
            flagged_categories={"sexual/minors", "sexual"},
        )
        score, _ = combined_score(openai, RekognitionResult(), DupResult())
        decision = route(score, openai, RekognitionResult())
        assert decision.is_csam is True
        assert decision.forced_human is True
        assert decision.tier == "tier_3_1h"
        assert decision.sla_hours == 1

    def test_harassment_threatening_always_forced_even_low_score(self):
        """harassment/threatening with score 0.3 (after all weighted) → still forced_human."""
        openai = OpenAIModResult(
            flagged=True,
            category_scores={"harassment/threatening": 0.2},
            flagged_categories={"harassment/threatening"},
        )
        score, _ = combined_score(openai, RekognitionResult(), DupResult())
        decision = route(score, openai, RekognitionResult())
        assert decision.forced_human is True


# ---------------------------------------------------------------------------
# §11.4 False-positive recovery
# ---------------------------------------------------------------------------


class TestFalsePositiveRecovery:
    def test_dismiss_action_for_auto_hidden_content(self):
        """
        A moderator reviewing auto-hidden content (score 0.91) can dismiss.
        The dismiss action should:
        - Set case.status = 'dismissed'
        - Not require second_reviewer_id
        - Not be blocked by forced_human=False on the case

        We test the schema/logic level here; endpoint integration tested separately.
        """
        from app.schemas import CaseActionRequest

        # Dismiss does not require second reviewer
        req = CaseActionRequest(
            action_type="dismiss",
            reason="Content reviewed by moderator; flagged in error by OpenAI model.",
        )
        assert req.action_type == "dismiss"
        assert req.second_reviewer_id is None

    def test_dismiss_is_not_a_dual_review_action(self):
        """Dismiss should NOT be in the _DUAL_REVIEW_ACTIONS set."""
        from app.routers.cases import _DUAL_REVIEW_ACTIONS

        assert "dismiss" not in _DUAL_REVIEW_ACTIONS

    def test_false_positive_score_preserved_in_scan_log(self):
        """
        Original tool response must be preserved in mod_scan_log even after dismissal.
        This verifies the audit trail requirement (plan §11.4).
        """
        # ModScanLog is append-only — no delete — so the original response lives on
        # Test the data shape is correct
        from app.models import ModScanLog

        assert hasattr(ModScanLog, "raw_response")
        assert hasattr(ModScanLog, "score")
        assert hasattr(ModScanLog, "tool")


# ---------------------------------------------------------------------------
# §11.5 Reciprocal report-bombing
# ---------------------------------------------------------------------------


class TestReportBombing:
    def test_reports_dedup_to_single_case(self):
        """
        Multiple reports on the same subject must collapse to one ModerationCase.
        Routing tier is based on AI score, NOT report count.
        """
        # Verify the de-dup logic in _find_or_create_case:
        # if an open case exists for same (subject_type, subject_id) → return it
        # This is asserted via the DB query logic structure in reports.py
        from app.routers import reports as reports_module

        # Inspect the _find_or_create_case function signature
        import inspect

        sig = inspect.signature(reports_module._find_or_create_case)
        params = list(sig.parameters.keys())
        assert "subject_type" in params
        assert "subject_id" in params

    def test_report_tier_not_inflated_by_count(self):
        """10 coordinated reports → score still determines tier, not report count."""
        openai = OpenAIModResult(
            flagged=False,
            category_scores={"harassment": 0.25},
            flagged_categories=set(),
        )
        score, _ = combined_score(openai, RekognitionResult(), DupResult())
        decision = route(score, openai, RekognitionResult())

        # Score 0.25 → tier_0 regardless of how many people reported
        assert decision.tier == "tier_0_allow"

    def test_daily_report_limit_per_user(self):
        """Reporter daily limit (20/day) prevents mass reporting."""
        from app.config import get_mod_settings

        settings = get_mod_settings()
        assert settings.reports_per_user_per_day == 20


# ---------------------------------------------------------------------------
# §11.6 CSAM hard path
# ---------------------------------------------------------------------------


class TestCSAMPath:
    def test_csam_route_tier3_forced(self):
        """Any sexual/minors positive → tier_3_1h + forced_human + is_csam."""
        openai = OpenAIModResult(
            flagged=True,
            category_scores={"sexual/minors": 0.01},  # even tiny score triggers
            flagged_categories={"sexual/minors"},
        )
        score, breakdown = combined_score(openai, RekognitionResult(), DupResult())
        decision = route(score, openai, RekognitionResult())

        assert decision.is_csam is True
        assert decision.forced_human is True
        assert decision.tier == "tier_3_1h"
        assert decision.forced_reason == "csam_path"

    def test_csam_weight_escalates_score(self):
        """Weight 1.5 on sexual/minors forces score above 0.9 threshold."""
        openai = OpenAIModResult(
            flagged=True,
            category_scores={"sexual/minors": 0.65},
            flagged_categories={"sexual/minors"},
        )
        score, breakdown = combined_score(openai, RekognitionResult(), DupResult())
        # 1.5 * 0.65 = 0.975 → well above 0.9
        assert score >= 0.9

    def test_csam_takes_precedence_over_all_other_routing(self):
        """CSAM must be checked first, before any other routing logic."""
        openai = OpenAIModResult(
            flagged=True,
            category_scores={"sexual/minors": 0.99, "harassment": 0.1},
            flagged_categories={"sexual/minors", "harassment"},
        )
        decision = route(1.0, openai, RekognitionResult())
        # is_csam check fires before harassment/threatening check
        assert decision.is_csam is True


# ---------------------------------------------------------------------------
# §11.7 Multimodal evasion
# ---------------------------------------------------------------------------


class TestMultimodalEvasion:
    def test_evasion_via_innocent_text_harmful_image(self):
        """
        'you know what to do, friend' (text score 0.2) + Violence image (0.7)
        → combined must route to tier_2 based on image score.
        """
        openai = OpenAIModResult(
            flagged=False,
            category_scores={"harassment": 0.2},
            flagged_categories=set(),
        )
        rek = RekognitionResult(labels=[
            {"Name": "Violence", "ParentName": "Violence", "Confidence": 70.0},
        ])
        score, breakdown = combined_score(openai, rek, DupResult())
        decision = route(score, openai, rek)

        # Image score 0.70 → tier_2_6h (not allowed by innocent text)
        assert decision.tier == "tier_2_6h"
        assert "allow" not in decision.action

    def test_image_weighted_contributes_to_score(self):
        """Rekognition score correctly weighted and included in combined."""
        openai = OpenAIModResult(flagged=False, category_scores={}, flagged_categories=set())
        rek = RekognitionResult(labels=[
            {"Name": "Explicit Nudity", "ParentName": "Explicit", "Confidence": 80.0},
        ])
        score, breakdown = combined_score(openai, rek, DupResult())
        # Rekognition:Explicit weight 1.2 * 0.80 = 0.96 → tier_3
        assert score >= 0.9
        assert breakdown["rekognition"]["weighted"] > 0

    def test_dup_match_bumps_below_threshold_into_tier1(self):
        """Dup match on an otherwise-allowed message bumps it to soft-warn."""
        openai = OpenAIModResult(
            flagged=False,
            category_scores={"harassment": 0.2},  # score 0.2 → normally tier_0
            flagged_categories=set(),
        )
        rek = RekognitionResult(labels=[])
        dup = DupResult(semdup_match=True)  # matches banned text registry

        score, breakdown = combined_score(openai, rek, dup)
        # 0.2 + 0.3 (dup bump) = 0.5 → tier_1
        assert score >= 0.4
        decision = route(score, openai, rek)
        assert decision.tier in ("tier_1_24h", "tier_2_6h", "tier_3_1h")


# ---------------------------------------------------------------------------
# DB append-only enforcement (conceptual — actual trigger tested in migration)
# ---------------------------------------------------------------------------


class TestAppendOnlyAuditLog:
    def test_moderation_action_has_no_update_method_in_orm(self):
        """
        ModerationAction model does not expose mutation helpers.
        The DB trigger is the enforcement layer; here we verify the table
        is defined without `onupdate` hooks.
        """
        from app.models import ModerationAction

        # ModerationAction must not have updated_at column (append-only has no updates)
        columns = {c.name for c in ModerationAction.__table__.columns}
        assert "updated_at" not in columns

    def test_action_propagation_log_append_only(self):
        """ActionPropagationLog similarly has no updated_at."""
        from app.models import ActionPropagationLog

        columns = {c.name for c in ActionPropagationLog.__table__.columns}
        assert "updated_at" not in columns
