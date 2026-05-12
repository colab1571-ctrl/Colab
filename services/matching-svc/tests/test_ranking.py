"""
matching-svc tests — ranking formula.

Tests the five-signal score formula with worked examples from plan §3.3:
  A→B: emb_sim=0.82, comp_voc=0.95, activity=0.86, health=0.75, rand=0.52
       score_B = 0.328 + 0.238 + 0.129 + 0.075 + 0.052 = 0.822

  A→C: emb_sim=0.71, comp_voc=0.50, activity=0.105, health=0.40, rand=0.48
       score_C = 0.284 + 0.125 + 0.016 + 0.040 + 0.048 = 0.513

Also covers: cold-start formula, activity decay, rand determinism, clamping.
"""

from __future__ import annotations

import math
import uuid
from datetime import date, datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from app.services.ranking import (
    AFFINITY_SEED,
    VOCATION_CATEGORIES,
    RankingWeights,
    activity_score,
    comp_voc_score,
    compute_score,
    rand_component,
)


TOLERANCE = 1e-3  # ±0.001 per spec AC-011


# ---------------------------------------------------------------------------
# Worked example A → B (plan §3.3)
# ---------------------------------------------------------------------------

class TestWorkedExampleAB:
    """
    Profile A (Indie Filmmaker) → Profile B (Composer/Music Producer)
    Expected score: 0.822
    """

    # Fix the random component to match the worked example
    VIEWER_ID = "profile-a"
    CANDIDATE_ID = "profile-b"
    TEST_DATE = date(2026, 5, 11)
    LAST_ACTIVE = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)  # 3 days ago

    def _fixed_rand(self, viewer_id, candidate_id, day=None):
        """Return 0.52 to match the worked example."""
        return 0.52

    def test_activity_3_days(self):
        """activity = exp(-0.05 × 3) ≈ 0.860"""
        with patch("app.services.ranking.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            score = activity_score(self.LAST_ACTIVE, lambda_=0.05)
        assert abs(score - math.exp(-0.05 * 3)) < TOLERANCE

    def test_score_b_formula(self):
        """
        Full formula for A→B:
        0.40×0.82 + 0.25×0.95 + 0.15×activity(3d) + 0.10×0.75 + 0.10×0.52
        """
        with patch("app.services.ranking.rand_component", side_effect=self._fixed_rand):
            with patch("app.services.ranking.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

                # Use exact activity from plan: 0.86
                total, emb, voc, act, rnd = compute_score(
                    viewer_id=self.VIEWER_ID,
                    candidate_id=self.CANDIDATE_ID,
                    emb_sim=0.82,
                    comp_voc=0.95,
                    last_active_at=self.LAST_ACTIVE,
                    health=0.75,
                    weights=RankingWeights(),
                    day=self.TEST_DATE,
                )

        # Verify components
        assert abs(emb - 0.82) < TOLERANCE
        assert abs(voc - 0.95) < TOLERANCE
        assert rnd == 0.52  # mocked

        # Verify total (use the actual activity from function, not hardcoded)
        expected = (
            0.40 * 0.82
            + 0.25 * 0.95
            + 0.15 * act
            + 0.10 * 0.75
            + 0.10 * 0.52
        )
        assert abs(total - expected) < TOLERANCE

    def test_score_b_is_approximately_0822(self):
        """
        With activity ≈ 0.86, total ≈ 0.822 per plan.
        Verify within broader tolerance since activity is computed dynamically.
        """
        with patch("app.services.ranking.rand_component", side_effect=self._fixed_rand):
            with patch("app.services.ranking.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

                total, *_ = compute_score(
                    viewer_id=self.VIEWER_ID,
                    candidate_id=self.CANDIDATE_ID,
                    emb_sim=0.82,
                    comp_voc=0.95,
                    last_active_at=self.LAST_ACTIVE,
                    health=0.75,
                    weights=RankingWeights(),
                    day=self.TEST_DATE,
                )
        # Plan says 0.822; allow ±0.02 for dynamic activity
        assert abs(total - 0.822) < 0.02, f"Expected ~0.822 got {total}"


# ---------------------------------------------------------------------------
# Worked example A → C (plan §3.3)
# ---------------------------------------------------------------------------

class TestWorkedExampleAC:
    """
    Profile A (Indie Filmmaker) → Profile C (Filmmaker, Austin TX, 45 days inactive)
    Expected score: 0.513
    """

    VIEWER_ID = "profile-a"
    CANDIDATE_ID = "profile-c"
    TEST_DATE = date(2026, 5, 11)
    LAST_ACTIVE = datetime(2026, 3, 27, 12, 0, 0, tzinfo=timezone.utc)  # 45 days ago

    def _fixed_rand(self, viewer_id, candidate_id, day=None):
        return 0.48

    def test_activity_45_days(self):
        """activity = exp(-0.05 × 45) ≈ 0.105"""
        with patch("app.services.ranking.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            score = activity_score(self.LAST_ACTIVE, lambda_=0.05)
        assert abs(score - math.exp(-0.05 * 45)) < TOLERANCE

    def test_score_c_formula(self):
        with patch("app.services.ranking.rand_component", side_effect=self._fixed_rand):
            with patch("app.services.ranking.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

                total, emb, voc, act, rnd = compute_score(
                    viewer_id=self.VIEWER_ID,
                    candidate_id=self.CANDIDATE_ID,
                    emb_sim=0.71,
                    comp_voc=0.50,
                    last_active_at=self.LAST_ACTIVE,
                    health=0.40,
                    weights=RankingWeights(),
                    day=self.TEST_DATE,
                )

        expected = (
            0.40 * 0.71
            + 0.25 * 0.50
            + 0.15 * act
            + 0.10 * 0.40
            + 0.10 * 0.48
        )
        assert abs(total - expected) < TOLERANCE

    def test_score_c_approximately_0513(self):
        with patch("app.services.ranking.rand_component", side_effect=self._fixed_rand):
            with patch("app.services.ranking.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

                total, *_ = compute_score(
                    viewer_id=self.VIEWER_ID,
                    candidate_id=self.CANDIDATE_ID,
                    emb_sim=0.71,
                    comp_voc=0.50,
                    last_active_at=self.LAST_ACTIVE,
                    health=0.40,
                    weights=RankingWeights(),
                    day=self.TEST_DATE,
                )
        assert abs(total - 0.513) < 0.02, f"Expected ~0.513 got {total}"

    def test_b_outranks_c(self):
        """Profile B (cross-discipline, active) must score higher than C (same vocation, inactive)."""
        viewer = "profile-a"
        test_date = date(2026, 5, 11)
        now = datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)

        with patch("app.services.ranking.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            score_b, *_ = compute_score(
                viewer_id=viewer,
                candidate_id="profile-b",
                emb_sim=0.82,
                comp_voc=0.95,
                last_active_at=datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc),
                health=0.75,
                day=test_date,
            )
            score_c, *_ = compute_score(
                viewer_id=viewer,
                candidate_id="profile-c",
                emb_sim=0.71,
                comp_voc=0.50,
                last_active_at=datetime(2026, 3, 27, 12, 0, 0, tzinfo=timezone.utc),
                health=0.40,
                day=test_date,
            )

        assert score_b > score_c, (
            f"Expected B ({score_b:.3f}) > C ({score_c:.3f})"
        )


# ---------------------------------------------------------------------------
# Activity decay
# ---------------------------------------------------------------------------

class TestActivityScore:
    def test_active_today(self):
        now = datetime.now(tz=timezone.utc)
        score = activity_score(now)
        assert abs(score - 1.0) < TOLERANCE

    def test_none_is_zero(self):
        assert activity_score(None) == 0.0

    def test_14_days_half_life(self):
        """λ=0.05 gives half-life of ln(2)/0.05 ≈ 13.86 days; score at 14d ≈ 0.497"""
        last = datetime.now(tz=timezone.utc) - timedelta(days=14)
        score = activity_score(last)
        expected = math.exp(-0.05 * 14)  # ≈ 0.497
        assert abs(score - expected) < TOLERANCE

    def test_90_days_near_zero(self):
        last = datetime.now(tz=timezone.utc) - timedelta(days=90)
        score = activity_score(last)
        assert score < 0.02  # effectively filtered out

    def test_clamped_to_0_1(self):
        future = datetime.now(tz=timezone.utc) + timedelta(days=10)
        score = activity_score(future)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Rand component determinism
# ---------------------------------------------------------------------------

class TestRandComponent:
    def test_deterministic_within_day(self):
        d = date(2026, 5, 11)
        r1 = rand_component("viewer-1", "candidate-1", d)
        r2 = rand_component("viewer-1", "candidate-1", d)
        assert r1 == r2

    def test_different_across_days(self):
        d1 = date(2026, 5, 11)
        d2 = date(2026, 5, 12)
        r1 = rand_component("viewer-1", "candidate-1", d1)
        r2 = rand_component("viewer-1", "candidate-1", d2)
        # Extremely unlikely to be equal (different seeds)
        assert r1 != r2

    def test_different_pairs_differ(self):
        d = date(2026, 5, 11)
        r1 = rand_component("viewer-1", "candidate-1", d)
        r2 = rand_component("viewer-1", "candidate-2", d)
        assert r1 != r2

    def test_bounded_0_to_1(self):
        d = date(2026, 5, 11)
        # Test with multiple UUIDs
        for i in range(50):
            val = rand_component(str(uuid.uuid4()), str(uuid.uuid4()), d)
            assert 0.0 <= val <= 1.0


# ---------------------------------------------------------------------------
# Cold-start formula
# ---------------------------------------------------------------------------

class TestColdStart:
    def test_emb_sim_zero_uses_cold_start_formula(self):
        """
        When emb_sim=0 (no embedding), the cold-start formula is:
          0.45×comp_voc + 0.25×activity + 0.20×health + 0.10×rand
        """
        with patch("app.services.ranking.rand_component", return_value=0.5):
            last = datetime.now(tz=timezone.utc) - timedelta(days=7)
            total, emb, voc, act, rnd = compute_score(
                viewer_id="new-user",
                candidate_id="some-profile",
                emb_sim=0.0,
                comp_voc=0.80,
                last_active_at=last,
                health=0.60,
            )

        expected = 0.45 * 0.80 + 0.25 * act + 0.20 * 0.60 + 0.10 * 0.5
        assert abs(total - expected) < TOLERANCE
        assert emb == 0.0

    def test_cold_start_produces_reasonable_score(self):
        """Even with no embedding, a well-matching profile should score > 0.4."""
        with patch("app.services.ranking.rand_component", return_value=0.5):
            last = datetime.now(tz=timezone.utc) - timedelta(days=1)
            total, *_ = compute_score(
                viewer_id="new-user",
                candidate_id="good-profile",
                emb_sim=0.0,
                comp_voc=0.95,
                last_active_at=last,
                health=0.80,
            )
        assert total > 0.4


# ---------------------------------------------------------------------------
# Clamping
# ---------------------------------------------------------------------------

class TestClamping:
    def test_oversized_inputs_clamped(self):
        with patch("app.services.ranking.rand_component", return_value=1.5):
            total, *_ = compute_score(
                viewer_id="v",
                candidate_id="c",
                emb_sim=1.5,
                comp_voc=1.2,
                last_active_at=None,
                health=1.3,
            )
        assert 0.0 <= total <= 1.0

    def test_negative_inputs_clamped(self):
        with patch("app.services.ranking.rand_component", return_value=0.0):
            total, *_ = compute_score(
                viewer_id="v",
                candidate_id="c",
                emb_sim=-0.5,
                comp_voc=-0.1,
                last_active_at=None,
                health=-0.3,
            )
        assert 0.0 <= total <= 1.0
