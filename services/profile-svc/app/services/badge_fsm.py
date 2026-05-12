"""
profile-svc — Valid Profile Badge state machine.

Pure-Python FSM; no I/O. All transitions are table-driven per plan §8.2.
State is persisted to Profile.badge_state by the caller.

States:
  unverified → email_verified → identity_pending → identity_approved
  → ai_review_pending → badge_granted | badge_held → badge_revoked

Events consumed from RabbitMQ + internal triggers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple


class BadgeState(str, Enum):
    unverified = "unverified"
    email_verified = "email_verified"
    identity_pending = "identity_pending"
    identity_approved = "identity_approved"
    ai_review_pending = "ai_review_pending"
    badge_granted = "badge_granted"
    badge_held = "badge_held"
    badge_revoked = "badge_revoked"


class BadgeEvent(str, Enum):
    # External events (RabbitMQ)
    user_email_verified = "user.email_verified"
    identity_inquiry_started = "identity.inquiry_started"
    identity_verified = "identity.verified"
    identity_declined = "identity.declined"
    identity_needs_review = "identity.needs_review"
    moderation_cleared = "moderation.cleared"
    moderation_upheld = "moderation.upheld"
    moderation_appeal_upheld = "moderation.appeal_upheld"
    user_deleted = "user.deleted"
    # Internal events
    ai_review_started = "ai.review.started"
    profile_review_completed_pass = "profile.review_completed.pass"
    profile_review_completed_soft_warn = "profile.review_completed.soft_warn"
    profile_review_completed_hide = "profile.review_completed.hide"
    profile_review_completed_severe = "profile.review_completed.severe"
    profile_updated_material = "profile.updated.material"
    badge_recheck_requested = "badge.recheck.requested"


@dataclass
class TransitionResult:
    new_state: BadgeState
    side_effects: list[str]  # event names to emit
    badge_held_reason: str | None = None
    terminal: bool = False


class _NoTransition(Exception):
    """Raised when a (state, event) pair has no defined transition."""


# ---------------------------------------------------------------------------
# Transition table: (current_state, event) → TransitionResult
# ---------------------------------------------------------------------------

_TRANSITIONS: dict[tuple[BadgeState, BadgeEvent], TransitionResult] = {
    # unverified
    (BadgeState.unverified, BadgeEvent.user_email_verified): TransitionResult(
        new_state=BadgeState.email_verified,
        side_effects=["profile.email_verified"],
    ),
    (BadgeState.unverified, BadgeEvent.user_deleted): TransitionResult(
        new_state=BadgeState.unverified,
        side_effects=[],
        terminal=True,
    ),

    # email_verified
    (BadgeState.email_verified, BadgeEvent.identity_inquiry_started): TransitionResult(
        new_state=BadgeState.identity_pending,
        side_effects=[],
    ),
    (BadgeState.email_verified, BadgeEvent.user_deleted): TransitionResult(
        new_state=BadgeState.email_verified,
        side_effects=[],
        terminal=True,
    ),

    # identity_pending
    (BadgeState.identity_pending, BadgeEvent.identity_verified): TransitionResult(
        new_state=BadgeState.identity_approved,
        side_effects=["ai.review.fire"],  # triggers AI review job
    ),
    (BadgeState.identity_pending, BadgeEvent.identity_declined): TransitionResult(
        new_state=BadgeState.email_verified,
        side_effects=[],
    ),
    (BadgeState.identity_pending, BadgeEvent.identity_needs_review): TransitionResult(
        new_state=BadgeState.identity_pending,
        side_effects=["moderation.queue.identity"],
    ),
    (BadgeState.identity_pending, BadgeEvent.user_deleted): TransitionResult(
        new_state=BadgeState.identity_pending,
        side_effects=[],
        terminal=True,
    ),

    # identity_approved
    (BadgeState.identity_approved, BadgeEvent.ai_review_started): TransitionResult(
        new_state=BadgeState.ai_review_pending,
        side_effects=[],
    ),
    (BadgeState.identity_approved, BadgeEvent.user_deleted): TransitionResult(
        new_state=BadgeState.identity_approved,
        side_effects=[],
        terminal=True,
    ),

    # ai_review_pending
    (BadgeState.ai_review_pending, BadgeEvent.profile_review_completed_pass): TransitionResult(
        new_state=BadgeState.badge_granted,
        side_effects=["profile.badge_granted"],
    ),
    (BadgeState.ai_review_pending, BadgeEvent.profile_review_completed_soft_warn): TransitionResult(
        new_state=BadgeState.badge_held,
        side_effects=["profile.badge_held"],
        badge_held_reason="soft_flag",
    ),
    (BadgeState.ai_review_pending, BadgeEvent.profile_review_completed_hide): TransitionResult(
        new_state=BadgeState.badge_held,
        side_effects=["profile.badge_held"],
        badge_held_reason="content_hidden",
    ),
    (BadgeState.ai_review_pending, BadgeEvent.profile_review_completed_severe): TransitionResult(
        new_state=BadgeState.badge_held,
        side_effects=["profile.badge_held", "user.temp_mute_requested"],
        badge_held_reason="severe_flag",
    ),
    (BadgeState.ai_review_pending, BadgeEvent.user_deleted): TransitionResult(
        new_state=BadgeState.ai_review_pending,
        side_effects=[],
        terminal=True,
    ),

    # badge_granted
    (BadgeState.badge_granted, BadgeEvent.moderation_upheld): TransitionResult(
        new_state=BadgeState.badge_revoked,
        side_effects=["profile.badge_revoked"],
    ),
    (BadgeState.badge_granted, BadgeEvent.profile_updated_material): TransitionResult(
        new_state=BadgeState.ai_review_pending,
        side_effects=["ai.review.fire"],
    ),
    (BadgeState.badge_granted, BadgeEvent.badge_recheck_requested): TransitionResult(
        new_state=BadgeState.ai_review_pending,
        side_effects=["ai.review.fire"],
    ),
    (BadgeState.badge_granted, BadgeEvent.user_deleted): TransitionResult(
        new_state=BadgeState.badge_granted,
        side_effects=[],
        terminal=True,
    ),

    # badge_held
    (BadgeState.badge_held, BadgeEvent.moderation_cleared): TransitionResult(
        new_state=BadgeState.badge_granted,
        side_effects=["profile.badge_granted"],
    ),
    (BadgeState.badge_held, BadgeEvent.moderation_upheld): TransitionResult(
        new_state=BadgeState.badge_revoked,
        side_effects=["profile.badge_revoked"],
    ),
    (BadgeState.badge_held, BadgeEvent.user_deleted): TransitionResult(
        new_state=BadgeState.badge_held,
        side_effects=[],
        terminal=True,
    ),

    # badge_revoked
    (BadgeState.badge_revoked, BadgeEvent.moderation_appeal_upheld): TransitionResult(
        new_state=BadgeState.badge_granted,
        side_effects=["profile.badge_granted"],
    ),
    (BadgeState.badge_revoked, BadgeEvent.user_deleted): TransitionResult(
        new_state=BadgeState.badge_revoked,
        side_effects=[],
        terminal=True,
    ),
}


def transition(current_state: BadgeState | str, event: BadgeEvent | str) -> TransitionResult:
    """
    Apply event to current state. Returns TransitionResult.
    Raises _NoTransition if (state, event) pair is not defined.
    """
    state = BadgeState(current_state)
    evt = BadgeEvent(event)
    key = (state, evt)
    if key not in _TRANSITIONS:
        raise _NoTransition(f"No transition from {state!r} on event {evt!r}")
    return _TRANSITIONS[key]


def score_to_event(score: float) -> BadgeEvent:
    """Map AI review aggregate score to the appropriate review-completed event."""
    if score < 0.40:
        return BadgeEvent.profile_review_completed_pass
    elif score < 0.70:
        return BadgeEvent.profile_review_completed_soft_warn
    elif score < 0.90:
        return BadgeEvent.profile_review_completed_hide
    else:
        return BadgeEvent.profile_review_completed_severe


def next_action(state: BadgeState | str) -> str | None:
    """Human-readable next action hint for the badge endpoint."""
    s = BadgeState(state)
    return {
        BadgeState.unverified: "verify_email",
        BadgeState.email_verified: "verify_identity",
        BadgeState.identity_pending: "verify_identity",
        BadgeState.identity_approved: "awaiting_ai_review",
        BadgeState.ai_review_pending: "awaiting_ai_review",
        BadgeState.badge_granted: None,
        BadgeState.badge_held: "mod_review",
        BadgeState.badge_revoked: None,
    }.get(s)
