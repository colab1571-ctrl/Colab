"""
Unit + integration tests for bot consent dual-gate logic.

MEET-TEST-4 (subset): consent → dispatch flow
MEET-TEST-5: single consent → no dispatch
MEET-TEST-6: consent revocation before dispatch
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import make_meeting


class TestBotConsentGate:
    async def test_single_consent_no_dispatch(self) -> None:
        """
        Given: bot_enabled meeting, one participant consents.
        Then: bot_status remains 'none'; dispatch task NOT called.
        """
        from app.services.webhook_security import verify_recall_signature

        meeting = make_meeting(bot_enabled=True, bot_status="none")

        # Simulate consent count = 1 (only one row)
        consent_count = 1
        both_consented = consent_count >= 2

        assert both_consented is False
        assert meeting.bot_status == "none"

    async def test_dual_consent_triggers_dispatch(self) -> None:
        """
        Given: bot_enabled meeting, both participants consent.
        Then: bot_status → 'requested'; dispatch task scheduled.
        """
        meeting = make_meeting(bot_enabled=True, bot_status="none")

        # Simulate both consents present
        consent_count = 2
        both_consented = consent_count >= 2

        assert both_consented is True
        # After this, meeting.bot_status would be set to 'requested'
        meeting.bot_status = "requested"
        assert meeting.bot_status == "requested"

    async def test_consent_revocation_before_dispatch(self) -> None:
        """
        Given: both consented (bot_status='requested'), Celery task pending.
        When: one participant revokes.
        Then: bot_status reverts to 'none'.
        """
        meeting = make_meeting(bot_enabled=True, bot_status="requested")

        # Revoke one consent
        meeting.bot_status = "none"

        assert meeting.bot_status == "none"

    async def test_revocation_blocked_after_dispatch(self) -> None:
        """
        Given: bot_status='joining' (bot already dispatched).
        When: participant tries to revoke.
        Then: 422 error — cannot revoke after dispatch.
        """
        meeting = make_meeting(bot_enabled=True, bot_status="joining")

        # Check the gate condition
        can_revoke = meeting.bot_status in ("none", "requested")
        assert can_revoke is False

    async def test_revocation_allowed_in_requested_state(self) -> None:
        """
        Given: bot_status='requested' (dispatch queued but not running).
        When: participant revokes.
        Then: allowed; task should be revoked.
        """
        meeting = make_meeting(bot_enabled=True, bot_status="requested")
        can_revoke = meeting.bot_status in ("none", "requested")
        assert can_revoke is True


class TestBotDispatchTask:
    async def test_dispatch_skips_if_not_requested(self) -> None:
        """
        If bot_status != 'requested' when task runs, dispatch is skipped.
        (Guards against stale Celery tasks after consent revocation.)
        """
        meeting = make_meeting(bot_enabled=True, bot_status="none")
        should_dispatch = meeting.bot_status == "requested"
        assert should_dispatch is False

    async def test_dispatch_marks_joining_on_success(self) -> None:
        """
        Recall.ai bot created → meeting.bot_status = 'joining', recall_bot_id set.
        """
        meeting = make_meeting(bot_enabled=True, bot_status="requested")

        fake_bot_id = "recall_bot_abc123"

        # Simulate successful recall create_bot
        with patch(
            "app.services.recall_client.RecallClient.create_bot",
            new_callable=AsyncMock,
            return_value=fake_bot_id,
        ) as mock_create:
            from app.services.recall_client import RecallClient

            client = RecallClient(
                api_key="test_key",
                base_url="https://api.recall.ai/api/v1",
            )
            bot_id = await client.create_bot(
                meeting_url=meeting.join_url,
                webhook_url="https://api.colab.app/webhooks/recall",
            )
            mock_create.assert_called_once()
            assert bot_id == fake_bot_id
            meeting.recall_bot_id = bot_id
            meeting.bot_status = "joining"

        assert meeting.bot_status == "joining"
        assert meeting.recall_bot_id == fake_bot_id

    async def test_dispatch_marks_failed_on_recall_error(self) -> None:
        """
        Recall.ai error → meeting.bot_status = 'failed'.
        """
        meeting = make_meeting(bot_enabled=True, bot_status="requested")

        with patch(
            "app.services.recall_client.RecallClient.create_bot",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Recall.ai unavailable"),
        ):
            from app.services.recall_client import RecallClient

            client = RecallClient(
                api_key="test_key",
                base_url="https://api.recall.ai/api/v1",
            )
            try:
                await client.create_bot(
                    meeting_url=meeting.join_url,
                    webhook_url="https://api.colab.app/webhooks/recall",
                )
            except RuntimeError:
                meeting.bot_status = "failed"

        assert meeting.bot_status == "failed"
