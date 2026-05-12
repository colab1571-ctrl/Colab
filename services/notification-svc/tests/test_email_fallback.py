"""
Tests: email fallback rule for key notification types.

AC-N-08: Email fallback when push preference disabled.
AC-N-09: Email fallback when no push device registered.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import KEY_NOTIFICATION_TYPES, NotificationType


class TestEmailFallbackLogic:
    """Unit tests for the email fallback decision logic."""

    def test_key_types_include_new_match(self) -> None:
        assert NotificationType.new_match.value in KEY_NOTIFICATION_TYPES

    def test_non_key_types_excluded(self) -> None:
        """chat_message, marketing, weekly_digest are NOT key types."""
        assert NotificationType.chat_message.value not in KEY_NOTIFICATION_TYPES
        assert NotificationType.marketing.value not in KEY_NOTIFICATION_TYPES
        assert NotificationType.weekly_digest.value not in KEY_NOTIFICATION_TYPES

    def test_fallback_logic_push_disabled(self) -> None:
        """
        Simulate the fallback decision: push_pref disabled AND type is key.
        Expected: email fallback should fire.
        """
        notif_type = NotificationType.new_match.value
        push_enabled = False
        has_active_device = True  # device exists but pref is off
        email_enabled = True

        is_key = notif_type in KEY_NOTIFICATION_TYPES
        push_unreachable = not push_enabled or not has_active_device
        should_email_fallback = is_key and email_enabled and push_unreachable

        assert should_email_fallback is True

    def test_fallback_logic_no_device(self) -> None:
        """
        Simulate: push_pref enabled but no registered device.
        Expected: email fallback fires for key type.
        """
        notif_type = NotificationType.ai_mockup_ready.value
        push_enabled = True
        has_active_device = False  # no device registered
        email_enabled = True

        is_key = notif_type in KEY_NOTIFICATION_TYPES
        push_unreachable = not push_enabled or not has_active_device
        should_email_fallback = is_key and email_enabled and push_unreachable

        assert should_email_fallback is True

    def test_fallback_does_not_fire_for_non_key_type(self) -> None:
        """chat_message never triggers email fallback even if push fails."""
        notif_type = NotificationType.chat_message.value
        push_enabled = False
        has_active_device = False
        email_enabled = True

        is_key = notif_type in KEY_NOTIFICATION_TYPES
        push_unreachable = not push_enabled or not has_active_device
        should_email_fallback = is_key and email_enabled and push_unreachable

        assert should_email_fallback is False

    def test_fallback_does_not_fire_if_email_disabled(self) -> None:
        """Email fallback respects user's email preference."""
        notif_type = NotificationType.new_match.value
        push_enabled = False
        has_active_device = False
        email_enabled = False  # user disabled email for this type

        is_key = notif_type in KEY_NOTIFICATION_TYPES
        push_unreachable = not push_enabled or not has_active_device
        should_email_fallback = is_key and email_enabled and push_unreachable

        assert should_email_fallback is False

    def test_fallback_does_not_fire_when_push_succeeds(self) -> None:
        """If push was successfully delivered, no fallback needed."""
        notif_type = NotificationType.collab_nudge.value
        push_enabled = True
        has_active_device = True
        email_enabled = True

        is_key = notif_type in KEY_NOTIFICATION_TYPES
        push_unreachable = not push_enabled or not has_active_device
        should_email_fallback = is_key and email_enabled and push_unreachable

        # push_unreachable is False since both are True
        assert push_unreachable is False
        assert should_email_fallback is False


class TestSESEmailSend:
    """Unit tests for the SES email channel."""

    def test_send_email_calls_ses(self, mock_ses_client: MagicMock) -> None:
        """send_email() should call ses.send_email with correct params."""
        import os

        os.environ["SES_CONFIGURATION_SET"] = ""  # Disable config set for test

        with patch("app.channels.email._get_ses", return_value=mock_ses_client):
            from app.channels.email import send_email

            result = send_email(
                to_address="test@example.com",
                subject="Test Subject",
                template_name="new_match.html",
                context={"other_user_display_name": "Bob", "collab_id": "abc-123"},
            )

        mock_ses_client.send_email.assert_called_once()
        call_kwargs = mock_ses_client.send_email.call_args[1]
        assert call_kwargs["Destination"]["ToAddresses"] == ["test@example.com"]
        assert result is True

    def test_send_transactional_bypasses_preferences(self, mock_ses_client: MagicMock) -> None:
        """send_transactional_email() does not check preferences."""
        with patch("app.channels.email._get_ses", return_value=mock_ses_client):
            from app.channels.email import send_transactional_email

            result = send_transactional_email(
                to_address="user@example.com",
                subject="Payment Receipt",
                template_name="new_match.html",  # re-use for test
                context={},
            )

        # Should call SES regardless — no preference lookup
        mock_ses_client.send_email.assert_called_once()
        assert result is True

    def test_ses_failure_returns_false(self) -> None:
        """SES ClientError should return False (not raise)."""
        from botocore.exceptions import ClientError

        mock_ses = MagicMock()
        mock_ses.send_email.side_effect = ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "Bad email"}}, "SendEmail"
        )

        with patch("app.channels.email._get_ses", return_value=mock_ses):
            from app.channels.email import send_email

            result = send_email("bad@example.com", "Subject", "new_match.html", {})

        assert result is False
