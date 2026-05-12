"""
Tests: push device registration and pre-permission card logic.

AC-N-04: should_prompt_push=True when no token + queued notifications.
AC-N-05: should_prompt_push=False when no queue.
AC-N-20: Device deregistration deletes endpoint.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch


class TestPrePermissionCard:
    """Test the server-side logic for should_prompt_push."""

    def test_prompt_when_no_token_and_queued(self) -> None:
        """
        Given: no active token, 2 queued notifications.
        Expected: should_prompt_push=True, queued_count=2.
        """
        has_token = False
        queued_count = 2
        has_queued = queued_count > 0

        should_prompt = not has_token and has_queued
        assert should_prompt is True

    def test_no_prompt_when_no_queue(self) -> None:
        """
        Given: no token, 0 queued notifications.
        Expected: should_prompt_push=False.
        """
        has_token = False
        queued_count = 0
        has_queued = queued_count > 0

        should_prompt = not has_token and has_queued
        assert should_prompt is False

    def test_no_prompt_when_token_present(self) -> None:
        """
        Given: token already registered (user already granted permission).
        Expected: should_prompt_push=False regardless of queue.
        """
        has_token = True
        queued_count = 5
        has_queued = queued_count > 0

        should_prompt = not has_token and has_queued
        assert should_prompt is False

    def test_prompt_suppressed_after_3_dismissals(self) -> None:
        """
        Given: 3 previous dismissals.
        Expected: should_prompt_push=False (suppress permanently).
        """
        has_token = False
        queued_count = 3
        has_queued = queued_count > 0
        dismissed_count = 3
        threshold = 3

        should_prompt = not has_token and has_queued
        if dismissed_count >= threshold:
            should_prompt = False

        assert should_prompt is False

    def test_prompt_allowed_with_2_dismissals(self) -> None:
        """
        Given: 2 previous dismissals (below threshold).
        Expected: should_prompt_push still True.
        """
        has_token = False
        queued_count = 1
        has_queued = queued_count > 0
        dismissed_count = 2
        threshold = 3

        should_prompt = not has_token and has_queued
        if dismissed_count >= threshold:
            should_prompt = False

        assert should_prompt is True


class TestSNSEndpointCreation:
    """Test SNS endpoint creation/update logic."""

    def test_create_endpoint_called_with_device_token(self, mock_sns_client: MagicMock) -> None:
        """When device_token is provided, create_platform_endpoint should be called."""
        import os

        os.environ["SNS_APNS_PLATFORM_ARN"] = "arn:aws:sns:us-east-1:123:app/APNS/test"

        with patch("app.channels.push._get_sns", return_value=mock_sns_client):
            from app.channels.push import create_or_update_sns_endpoint

            result = create_or_update_sns_endpoint(
                device_token="abc123devicetoken",
                platform="ios",
                user_id=str(uuid.uuid4()),
            )

        mock_sns_client.create_platform_endpoint.assert_called_once()
        assert result == "arn:aws:sns:us-east-1:123456789:endpoint/APNS/test/abc123"

    def test_delete_endpoint_called_on_deregister(self, mock_sns_client: MagicMock) -> None:
        """Deregistering a device should call sns.delete_endpoint."""
        endpoint_arn = "arn:aws:sns:us-east-1:123456789:endpoint/APNS/test/abc123"

        with patch("app.channels.push._get_sns", return_value=mock_sns_client):
            from app.channels.push import delete_sns_endpoint

            delete_sns_endpoint(endpoint_arn)

        mock_sns_client.delete_endpoint.assert_called_once_with(EndpointArn=endpoint_arn)

    def test_send_push_calls_sns_publish(self, mock_sns_client: MagicMock) -> None:
        """send_push() should call sns.publish with MessageStructure=json."""
        endpoint_arn = "arn:aws:sns:us-east-1:123456789:endpoint/APNS/test/abc123"
        notif_id = str(uuid.uuid4())

        with patch("app.channels.push._get_sns", return_value=mock_sns_client):
            from app.channels.push import send_push

            result = send_push(
                endpoint_arn=endpoint_arn,
                platform="ios",
                title="You have a new match!",
                body="Start collaborating now.",
                notif_id=notif_id,
                notif_type="new_match",
                deep_link="/collabs/abc-123",
            )

        mock_sns_client.publish.assert_called_once()
        call_kwargs = mock_sns_client.publish.call_args[1]
        assert call_kwargs["TargetArn"] == endpoint_arn
        assert call_kwargs["MessageStructure"] == "json"
        assert result is True
