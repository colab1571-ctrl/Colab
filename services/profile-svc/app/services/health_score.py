"""
profile-svc — Profile health score computation.

Formula per plan §6:
  health = 100 * (0.40 * completeness + 0.30 * activity + 0.30 * feedback)

Weights configurable via settings. Score float 0–100 persisted on Profile.
Recomputed:
  (a) synchronously on profile mutation (debounced 60s via Redis lock)
  (b) nightly via Celery Beat for all profiles
  (c) on feedback.created events from collab-svc
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.profile import Profile


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Completeness sub-score
# ---------------------------------------------------------------------------

def compute_completeness(profile: "Profile", identity_approved: bool = False) -> float:
    """
    Returns completeness in [0, 1] per the weighted checklist in §6.1.
    portfolio_items should only count those with ai_review_status='passed'.
    """
    score = 0.0

    if profile.display_name:
        score += 0.05

    if profile.location_point and profile.location_city:
        score += 0.10

    # Primary vocation
    primary_vocations = [v for v in profile.vocations if v.is_primary]
    if primary_vocations:
        score += 0.10

    # Bio ≥ 60 chars
    if profile.bio and len(profile.bio) >= 60:
        score += 0.08

    if profile.obsessed_with:
        score += 0.05

    # Portfolio: up to 0.30 (linear 0→6 items passed review, capped)
    passed_items = [p for p in profile.portfolio_items if p.ai_review_status == "passed"]
    portfolio_score = _clamp(len(passed_items) / 6.0) * 0.30
    score += portfolio_score

    if profile.external_links:
        score += 0.10

    if profile.personality_answers:
        score += 0.05

    if profile.experience_level is not None:
        score += 0.04

    if profile.looking_for:
        score += 0.06

    if profile.past_experience:
        score += 0.04

    # Selfie+liveness approved (identity_approved flag from identity-svc)
    if identity_approved:
        score += 0.03

    return _clamp(score)


# ---------------------------------------------------------------------------
# Activity sub-score
# ---------------------------------------------------------------------------

def compute_activity(
    profile: "Profile",
    login_days_last_28: int = 0,
    portfolio_updates_last_90d: int = 0,
) -> float:
    """
    Returns activity in [0, 1] per §6.2.
    login_days_last_28: distinct login days in last 28 days (from auth-svc, cached).
    portfolio_updates_last_90d: portfolio additions/edits in last 90 days.
    """
    now = datetime.now(tz=timezone.utc)

    # Recency: exponential decay on last_active_at with 14-day half-life
    if profile.last_active_at:
        days_since = (now - profile.last_active_at).total_seconds() / 86400
        recency = math.exp(-days_since / 14.0)
    else:
        recency = 0.0

    # Weekly logins: distinct days in last 28 / 14, cap 1.0
    weekly_logins = _clamp(login_days_last_28 / 14.0)

    # Portfolio freshness: additions/edits in last 90d / 3, cap 1.0
    portfolio_freshness = _clamp(portfolio_updates_last_90d / 3.0)

    activity = 0.4 * recency + 0.3 * weekly_logins + 0.3 * portfolio_freshness
    return _clamp(activity)


# ---------------------------------------------------------------------------
# Feedback sub-score
# ---------------------------------------------------------------------------

def compute_feedback(thumbs_up: int = 0, thumbs_down: int = 0, distinct_positive_tags: int = 0) -> float:
    """
    Returns feedback score in [0, 1] per §6.3.
    New profiles (n=0) get 0.5 (neutral prior).
    """
    n = thumbs_up + thumbs_down
    if n == 0:
        return 0.5  # neutral prior

    laplace_ratio = (thumbs_up + 1) / (n + 2)
    volume_factor = _clamp(n / 10.0)
    tag_boost = _clamp(distinct_positive_tags * 0.02, hi=0.1)
    return _clamp(laplace_ratio * volume_factor + tag_boost)


# ---------------------------------------------------------------------------
# Composite health score
# ---------------------------------------------------------------------------

def compute_health_score(
    profile: "Profile",
    identity_approved: bool = False,
    login_days_last_28: int = 0,
    portfolio_updates_last_90d: int = 0,
    thumbs_up: int = 0,
    thumbs_down: int = 0,
    distinct_positive_tags: int = 0,
    w_completeness: float = 0.40,
    w_activity: float = 0.30,
    w_feedback: float = 0.30,
) -> float:
    """Compute composite health score in [0, 100]."""
    completeness = compute_completeness(profile, identity_approved=identity_approved)
    activity = compute_activity(
        profile,
        login_days_last_28=login_days_last_28,
        portfolio_updates_last_90d=portfolio_updates_last_90d,
    )
    feedback = compute_feedback(thumbs_up, thumbs_down, distinct_positive_tags)
    return _clamp(100.0 * (w_completeness * completeness + w_activity * activity + w_feedback * feedback), 0.0, 100.0)
