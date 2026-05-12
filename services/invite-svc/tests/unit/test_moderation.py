"""
Unit tests for synopsis moderation client.

Covers:
  - AC-009: Flagged synopsis (score >= 0.4) raises SynopsisFlagged, no DB insert
  - Clean synopsis (score < 0.4) returns None (allow)
  - Moderation timeout → allow (risk-accept R-004)
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import respx

from app.services.moderation import SynopsisFlagged, scan_synopsis
from app.config import get_settings

settings = get_settings()


@pytest.mark.asyncio
@respx.mock
async def test_clean_synopsis_returns_none():
    """Score < 0.4 → scan_synopsis returns None (allowed)."""
    invite_id = uuid.uuid4()
    from_profile_id = uuid.uuid4()

    respx.post(f"{settings.moderation_svc_url}/internal/scan/text").mock(
        return_value=httpx.Response(
            200,
            json={
                "score": 0.1,
                "breakdown": {},
                "decision": "allow",
                "case_id": None,
                "action": "allow_log",
                "tier": "tier_0_allow",
                "forced_human": False,
            },
        )
    )

    result = await scan_synopsis("Let's make music together", from_profile_id, invite_id)
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_flagged_synopsis_raises_exception():
    """AC-009: Score >= 0.4 raises SynopsisFlagged with reason."""
    invite_id = uuid.uuid4()
    from_profile_id = uuid.uuid4()
    case_id = str(uuid.uuid4())

    respx.post(f"{settings.moderation_svc_url}/internal/scan/text").mock(
        return_value=httpx.Response(
            200,
            json={
                "score": 0.75,
                "breakdown": {"harassment": 0.8, "violence": 0.1},
                "decision": "hide",
                "case_id": case_id,
                "action": "hide_content_queue",
                "tier": "tier_2_hide",
                "forced_human": True,
            },
        )
    )

    with pytest.raises(SynopsisFlagged) as exc_info:
        await scan_synopsis("offensive content here", from_profile_id, invite_id)

    exc = exc_info.value
    assert exc.reason is not None
    assert "harassment" in exc.reason
    assert exc.case_id == uuid.UUID(case_id)


@pytest.mark.asyncio
@respx.mock
async def test_moderation_timeout_allows(monkeypatch):
    """R-004: Timeout on moderation → allow (risk-accept)."""
    invite_id = uuid.uuid4()
    from_profile_id = uuid.uuid4()

    respx.post(f"{settings.moderation_svc_url}/internal/scan/text").mock(
        side_effect=httpx.TimeoutException("timeout")
    )

    # Should NOT raise; returns None (allow)
    result = await scan_synopsis("test content", from_profile_id, invite_id)
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_moderation_error_allows():
    """Any moderation-svc error → allow (fail-open policy)."""
    invite_id = uuid.uuid4()
    from_profile_id = uuid.uuid4()

    respx.post(f"{settings.moderation_svc_url}/internal/scan/text").mock(
        return_value=httpx.Response(500, json={"detail": "internal error"})
    )

    # Should NOT raise; returns None
    result = await scan_synopsis("test content", from_profile_id, invite_id)
    assert result is None
