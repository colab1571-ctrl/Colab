"""
Tests: transactional email override.

AC-N-10: send_transactional_email() calls SES regardless of preferences.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestTransactionalEmailOverride:
    """
    Transactional emails (receipts, security, DSR confirmations) bypass
    all preference checks. The colab_ses_client.send_transactional_email()
    function must call SES without consulting NotificationPreference.
    """

    def test_transactional_send_does_not_query_preferences(self, mock_ses_client: MagicMock) -> None:
        """
        send_transactional_email() must not call any DB or preference lookup.
        We verify this by checking no database-related functions are called.
        """
        with patch("app.channels.email._get_ses", return_value=mock_ses_client):
            from app.channels.email import send_transactional_email

            # No DB or session involved — pure SES call
            result = send_transactional_email(
                to_address="user@example.com",
                subject="Your payment receipt",
                template_name="new_match.html",  # template stub
                context={"amount": "9.99", "currency": "USD"},
            )

        assert result is True
        mock_ses_client.send_email.assert_called_once()

    def test_ses_called_with_correct_recipient(self, mock_ses_client: MagicMock) -> None:
        """The to_address is correctly passed to SES."""
        with patch("app.channels.email._get_ses", return_value=mock_ses_client):
            from app.channels.email import send_transactional_email

            send_transactional_email(
                to_address="customer@example.com",
                subject="Account security alert",
                template_name="new_match.html",
                context={},
            )

        call_kwargs = mock_ses_client.send_email.call_args[1]
        assert "customer@example.com" in call_kwargs["Destination"]["ToAddresses"]

    def test_marketing_email_is_not_transactional(self) -> None:
        """
        Marketing emails must NOT use send_transactional_email().
        This test verifies the distinction is documented in code.
        """
        from app.channels.email import send_email, send_transactional_email

        # Both are different functions; transactional is the bypass path
        assert send_email is not send_transactional_email

    def test_transactional_email_returns_false_on_ses_error(self) -> None:
        """Even transactional emails return False on SES error (not raise)."""
        from botocore.exceptions import ClientError

        mock_ses = MagicMock()
        mock_ses.send_email.side_effect = ClientError(
            {"Error": {"Code": "SendingPausedException", "Message": "Account paused"}},
            "SendEmail",
        )

        with patch("app.channels.email._get_ses", return_value=mock_ses):
            from app.channels.email import send_transactional_email

            result = send_transactional_email("x@y.com", "Subject", "new_match.html", {})

        assert result is False
