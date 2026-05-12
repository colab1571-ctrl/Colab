"""
invite-svc — Pre-send synopsis moderation via moderation-svc.

Calls POST /internal/scan/text synchronously.
Timeout: 200ms (R-004). On timeout → allow + log for deferred review.
Score threshold: 0.4 (spec §006 plan §5).
"""

from __future__ import annotations

import logging
import uuid

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class SynopsisFlagged(Exception):
    """Raised when synopsis scores >= threshold."""

    def __init__(self, reason: str | None = None, case_id: uuid.UUID | None = None) -> None:
        self.reason = reason
        self.case_id = case_id
        super().__init__(f"Synopsis flagged: {reason}")


async def scan_synopsis(
    synopsis: str,
    from_profile_id: uuid.UUID,
    invite_id: uuid.UUID,
) -> uuid.UUID | None:
    """
    Scan synopsis through moderation-svc /internal/scan/text.

    Returns mod_case_id if a case was opened (score in warn/hide range but below auto-reject),
    raises SynopsisFlagged if score >= 0.4.
    Returns None if clean.

    On timeout (200ms) → allow + log for deferred review (R-004 risk-accept).
    """
    settings = get_settings()

    ctx = {
        "subject_type": "invite_synopsis",
        "subject_id": str(invite_id),
        "owner_user_id": str(from_profile_id),
        "idempotency_key": f"invite-synopsis:{invite_id}",
    }

    try:
        async with httpx.AsyncClient(
            timeout=settings.moderation_timeout_seconds
        ) as client:
            resp = await client.post(
                f"{settings.moderation_svc_url}/internal/scan/text",
                json={"text": synopsis, "ctx": ctx},
                headers={"X-Internal-Service": "invite-svc"},
            )
            resp.raise_for_status()
            data = resp.json()

    except httpx.TimeoutException:
        # R-004: allow on timeout; log for async deferred review
        logger.warning(
            "moderation-svc timeout scanning invite synopsis; allowing (deferred review). "
            "invite_id=%s from=%s",
            invite_id,
            from_profile_id,
        )
        return None
    except Exception as exc:
        logger.error(
            "moderation-svc error scanning synopsis (allowing): %s. invite_id=%s",
            exc,
            invite_id,
        )
        return None

    score: float = data.get("score", 0.0)
    threshold = settings.synopsis_flag_threshold

    if score >= threshold:
        # Extract human-readable reason from decision breakdown
        breakdown: dict = data.get("breakdown", {})
        reasons = [cat for cat, val in breakdown.items() if val and val > 0.3]
        reason = ", ".join(reasons) if reasons else data.get("decision", "policy_violation")
        case_id_raw = data.get("case_id")
        case_id = uuid.UUID(case_id_raw) if case_id_raw else None
        raise SynopsisFlagged(reason=reason, case_id=case_id)

    # Clean or sub-threshold — return case_id if one was opened for logging
    case_id_raw = data.get("case_id")
    return uuid.UUID(case_id_raw) if case_id_raw else None
