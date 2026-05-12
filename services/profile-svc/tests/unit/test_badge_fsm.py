"""
Tests: Badge FSM — all 20+ transitions per plan §8.2.
Run: pytest tests/unit/test_badge_fsm.py --cov=app.services.badge_fsm --cov-fail-under=100 -q
"""

import pytest

from app.services.badge_fsm import (
    BadgeEvent,
    BadgeState,
    _NoTransition,
    next_action,
    score_to_event,
    transition,
)


# ---------------------------------------------------------------------------
# Transition coverage — one test per row in the plan §8.2 table
# ---------------------------------------------------------------------------

class TestUnverifiedTransitions:
    def test_email_verified(self):
        r = transition(BadgeState.unverified, BadgeEvent.user_email_verified)
        assert r.new_state == BadgeState.email_verified
        assert "profile.email_verified" in r.side_effects

    def test_user_deleted(self):
        r = transition(BadgeState.unverified, BadgeEvent.user_deleted)
        assert r.terminal is True

    def test_no_identity_inquiry_from_unverified(self):
        with pytest.raises(_NoTransition):
            transition(BadgeState.unverified, BadgeEvent.identity_inquiry_started)


class TestEmailVerifiedTransitions:
    def test_identity_inquiry_started(self):
        r = transition(BadgeState.email_verified, BadgeEvent.identity_inquiry_started)
        assert r.new_state == BadgeState.identity_pending

    def test_user_deleted(self):
        r = transition(BadgeState.email_verified, BadgeEvent.user_deleted)
        assert r.terminal is True


class TestIdentityPendingTransitions:
    def test_identity_verified(self):
        r = transition(BadgeState.identity_pending, BadgeEvent.identity_verified)
        assert r.new_state == BadgeState.identity_approved
        assert "ai.review.fire" in r.side_effects

    def test_identity_declined(self):
        r = transition(BadgeState.identity_pending, BadgeEvent.identity_declined)
        assert r.new_state == BadgeState.email_verified
        assert not r.side_effects

    def test_identity_needs_review(self):
        r = transition(BadgeState.identity_pending, BadgeEvent.identity_needs_review)
        assert r.new_state == BadgeState.identity_pending
        assert "moderation.queue.identity" in r.side_effects

    def test_user_deleted(self):
        r = transition(BadgeState.identity_pending, BadgeEvent.user_deleted)
        assert r.terminal is True


class TestIdentityApprovedTransitions:
    def test_ai_review_started(self):
        r = transition(BadgeState.identity_approved, BadgeEvent.ai_review_started)
        assert r.new_state == BadgeState.ai_review_pending

    def test_user_deleted(self):
        r = transition(BadgeState.identity_approved, BadgeEvent.user_deleted)
        assert r.terminal is True


class TestAIReviewPendingTransitions:
    def test_pass(self):
        r = transition(BadgeState.ai_review_pending, BadgeEvent.profile_review_completed_pass)
        assert r.new_state == BadgeState.badge_granted
        assert "profile.badge_granted" in r.side_effects
        assert r.badge_held_reason is None

    def test_soft_warn(self):
        r = transition(BadgeState.ai_review_pending, BadgeEvent.profile_review_completed_soft_warn)
        assert r.new_state == BadgeState.badge_held
        assert r.badge_held_reason == "soft_flag"
        assert "profile.badge_held" in r.side_effects

    def test_hide(self):
        r = transition(BadgeState.ai_review_pending, BadgeEvent.profile_review_completed_hide)
        assert r.new_state == BadgeState.badge_held
        assert r.badge_held_reason == "content_hidden"

    def test_severe(self):
        r = transition(BadgeState.ai_review_pending, BadgeEvent.profile_review_completed_severe)
        assert r.new_state == BadgeState.badge_held
        assert r.badge_held_reason == "severe_flag"
        assert "user.temp_mute_requested" in r.side_effects

    def test_user_deleted(self):
        r = transition(BadgeState.ai_review_pending, BadgeEvent.user_deleted)
        assert r.terminal is True


class TestBadgeGrantedTransitions:
    def test_moderation_upheld(self):
        r = transition(BadgeState.badge_granted, BadgeEvent.moderation_upheld)
        assert r.new_state == BadgeState.badge_revoked
        assert "profile.badge_revoked" in r.side_effects

    def test_profile_updated_material(self):
        r = transition(BadgeState.badge_granted, BadgeEvent.profile_updated_material)
        assert r.new_state == BadgeState.ai_review_pending
        assert "ai.review.fire" in r.side_effects

    def test_badge_recheck_requested(self):
        r = transition(BadgeState.badge_granted, BadgeEvent.badge_recheck_requested)
        assert r.new_state == BadgeState.ai_review_pending

    def test_user_deleted(self):
        r = transition(BadgeState.badge_granted, BadgeEvent.user_deleted)
        assert r.terminal is True


class TestBadgeHeldTransitions:
    def test_moderation_cleared(self):
        r = transition(BadgeState.badge_held, BadgeEvent.moderation_cleared)
        assert r.new_state == BadgeState.badge_granted
        assert "profile.badge_granted" in r.side_effects

    def test_moderation_upheld(self):
        r = transition(BadgeState.badge_held, BadgeEvent.moderation_upheld)
        assert r.new_state == BadgeState.badge_revoked

    def test_user_deleted(self):
        r = transition(BadgeState.badge_held, BadgeEvent.user_deleted)
        assert r.terminal is True


class TestBadgeRevokedTransitions:
    def test_appeal_upheld(self):
        r = transition(BadgeState.badge_revoked, BadgeEvent.moderation_appeal_upheld)
        assert r.new_state == BadgeState.badge_granted
        assert "profile.badge_granted" in r.side_effects

    def test_user_deleted(self):
        r = transition(BadgeState.badge_revoked, BadgeEvent.user_deleted)
        assert r.terminal is True

    def test_no_random_event(self):
        with pytest.raises(_NoTransition):
            transition(BadgeState.badge_revoked, BadgeEvent.user_email_verified)


# ---------------------------------------------------------------------------
# Score → event mapping
# ---------------------------------------------------------------------------

class TestScoreToEvent:
    def test_below_40_is_pass(self):
        assert score_to_event(0.0) == BadgeEvent.profile_review_completed_pass
        assert score_to_event(0.39) == BadgeEvent.profile_review_completed_pass

    def test_40_to_70_is_soft_warn(self):
        assert score_to_event(0.40) == BadgeEvent.profile_review_completed_soft_warn
        assert score_to_event(0.55) == BadgeEvent.profile_review_completed_soft_warn
        assert score_to_event(0.699) == BadgeEvent.profile_review_completed_soft_warn

    def test_70_to_90_is_hide(self):
        assert score_to_event(0.70) == BadgeEvent.profile_review_completed_hide
        assert score_to_event(0.89) == BadgeEvent.profile_review_completed_hide

    def test_90_plus_is_severe(self):
        assert score_to_event(0.90) == BadgeEvent.profile_review_completed_severe
        assert score_to_event(1.0) == BadgeEvent.profile_review_completed_severe


# ---------------------------------------------------------------------------
# next_action hints
# ---------------------------------------------------------------------------

class TestNextAction:
    def test_unverified_hint(self):
        assert next_action(BadgeState.unverified) == "verify_email"

    def test_email_verified_hint(self):
        assert next_action(BadgeState.email_verified) == "verify_identity"

    def test_badge_granted_hint(self):
        assert next_action(BadgeState.badge_granted) is None

    def test_badge_held_hint(self):
        assert next_action(BadgeState.badge_held) == "mod_review"

    def test_awaiting_review_hints(self):
        assert next_action(BadgeState.ai_review_pending) == "awaiting_ai_review"
        assert next_action(BadgeState.identity_approved) == "awaiting_ai_review"


# ---------------------------------------------------------------------------
# String inputs (from DB values)
# ---------------------------------------------------------------------------

class TestStringInputs:
    def test_string_state_and_event(self):
        r = transition("unverified", "user.email_verified")
        assert r.new_state == BadgeState.email_verified

    def test_invalid_state_raises(self):
        with pytest.raises(ValueError):
            transition("not_a_state", BadgeEvent.user_email_verified)

    def test_invalid_event_raises(self):
        with pytest.raises(ValueError):
            transition(BadgeState.unverified, "not.an.event")
