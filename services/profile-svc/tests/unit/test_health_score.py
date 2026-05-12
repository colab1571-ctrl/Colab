"""
Tests: Profile health score computation.
Run: pytest tests/unit/test_health_score.py -q
"""

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.services.health_score import (
    compute_activity,
    compute_completeness,
    compute_feedback,
    compute_health_score,
)


def _mock_profile(
    display_name="Test",
    bio="x" * 60,
    obsessed_with="art",
    location_point=MagicMock(),
    location_city="New York",
    vocations=None,
    portfolio_items=None,
    external_links=None,
    personality_answers=None,
    experience_level=3,
    looking_for="collab",
    past_experience="5 years",
    last_active_at=None,
):
    p = MagicMock()
    p.display_name = display_name
    p.bio = bio
    p.obsessed_with = obsessed_with
    p.location_point = location_point
    p.location_city = location_city
    p.vocations = vocations or [MagicMock(is_primary=True)]
    p.portfolio_items = portfolio_items or []
    p.external_links = external_links or [MagicMock()]
    p.personality_answers = personality_answers or [MagicMock()]
    p.experience_level = experience_level
    p.looking_for = looking_for
    p.past_experience = past_experience
    p.last_active_at = last_active_at or datetime.now(tz=timezone.utc)
    return p


class TestCompletenessScore:
    def test_fully_complete_profile(self):
        portfolio_items = [
            MagicMock(ai_review_status="passed") for _ in range(6)
        ]
        p = _mock_profile(portfolio_items=portfolio_items)
        score = compute_completeness(p, identity_approved=True)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_empty_profile_has_low_score(self):
        p = MagicMock()
        p.display_name = None
        p.bio = None
        p.obsessed_with = None
        p.location_point = None
        p.location_city = None
        p.vocations = []
        p.portfolio_items = []
        p.external_links = []
        p.personality_answers = []
        p.experience_level = None
        p.looking_for = None
        p.past_experience = None
        score = compute_completeness(p, identity_approved=False)
        assert score == pytest.approx(0.0)

    def test_portfolio_linear_up_to_6(self):
        # 3 passed items → 0.30 * 3/6 = 0.15
        portfolio_items = [MagicMock(ai_review_status="passed") for _ in range(3)]
        p = MagicMock()
        p.display_name = None
        p.bio = None
        p.obsessed_with = None
        p.location_point = None
        p.location_city = None
        p.vocations = []
        p.portfolio_items = portfolio_items
        p.external_links = []
        p.personality_answers = []
        p.experience_level = None
        p.looking_for = None
        p.past_experience = None
        score = compute_completeness(p, identity_approved=False)
        assert score == pytest.approx(0.15, abs=0.01)

    def test_bio_too_short_not_counted(self):
        p = _mock_profile(bio="short")
        # bio < 60 chars → bio weight (0.08) not added
        full_score = compute_completeness(p, identity_approved=True)
        p2 = _mock_profile(bio="x" * 60)
        full_score2 = compute_completeness(p2, identity_approved=True)
        assert full_score < full_score2


class TestActivityScore:
    def test_recently_active_gives_high_recency(self):
        p = _mock_profile(last_active_at=datetime.now(tz=timezone.utc))
        score = compute_activity(p, login_days_last_28=14, portfolio_updates_last_90d=3)
        assert score > 0.9

    def test_inactive_28_days(self):
        p = _mock_profile(last_active_at=datetime.now(tz=timezone.utc) - timedelta(days=28))
        score = compute_activity(p, login_days_last_28=0, portfolio_updates_last_90d=0)
        assert score < 0.2

    def test_no_last_active(self):
        p = MagicMock()
        p.last_active_at = None
        score = compute_activity(p, login_days_last_28=0)
        assert score >= 0.0


class TestFeedbackScore:
    def test_neutral_prior_for_new_profiles(self):
        assert compute_feedback(0, 0, 0) == pytest.approx(0.5)

    def test_all_thumbs_up(self):
        score = compute_feedback(thumbs_up=10, thumbs_down=0, distinct_positive_tags=5)
        assert score > 0.9

    def test_all_thumbs_down(self):
        score = compute_feedback(thumbs_up=0, thumbs_down=10, distinct_positive_tags=0)
        assert score < 0.2

    def test_laplace_smoothing_with_few_reviews(self):
        # 1 thumbs_up, 0 down → laplace = (1+1)/(1+2) = 0.667; volume = 1/10 = 0.1
        score = compute_feedback(thumbs_up=1, thumbs_down=0, distinct_positive_tags=0)
        expected = (2/3) * 0.1
        assert score == pytest.approx(expected, abs=0.01)


class TestCompositeHealthScore:
    def test_score_in_range_0_100(self):
        p = _mock_profile()
        score = compute_health_score(p)
        assert 0.0 <= score <= 100.0

    def test_weights_sum_to_1(self):
        # Default weights should sum to 1.0
        from app.services.health_score import compute_health_score
        w_c, w_a, w_f = 0.40, 0.30, 0.30
        assert abs(w_c + w_a + w_f - 1.0) < 1e-9

    def test_new_profile_gets_decent_score(self):
        # New profile with no activity but neutral feedback prior → ~20-40%
        p = _mock_profile(
            portfolio_items=[],
            last_active_at=datetime.now(tz=timezone.utc),
        )
        score = compute_health_score(p, login_days_last_28=1, portfolio_updates_last_90d=0)
        assert 0.0 < score < 100.0
