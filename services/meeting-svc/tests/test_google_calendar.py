"""
Unit tests for GoogleCalendarClient.

MEET-TEST-1: success, idempotency, retry exhaustion.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from app.services.google_calendar import GoogleCalendarClient


FAKE_SA_JSON = """{
    "type": "service_account",
    "project_id": "colab-test",
    "private_key_id": "key123",
    "private_key": "FAKE",
    "client_email": "meeting-bot@colab-test.iam.gserviceaccount.com",
    "client_id": "123",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token"
}"""

FAKE_JOIN_URL = "https://meet.google.com/abc-defg-hij"

FAKE_GCAL_RESPONSE = {
    "id": "event_id_123",
    "status": "confirmed",
    "conferenceData": {
        "entryPoints": [
            {"entryPointType": "video", "uri": FAKE_JOIN_URL},
        ]
    },
}

FAKE_TOKEN_RESPONSE = {
    "access_token": "fake_token_xyz",
    "expires_in": 3600,
    "token_type": "Bearer",
}


@pytest.fixture
def gcal_client() -> GoogleCalendarClient:
    return GoogleCalendarClient(
        service_account_json=FAKE_SA_JSON,
        calendar_id="test_calendar",
    )


@pytest.fixture
def start_dt() -> datetime:
    return datetime(2026, 6, 1, 15, 0, 0, tzinfo=UTC)


class TestCreateEvent:
    @respx.mock
    async def test_create_event_success(
        self, gcal_client: GoogleCalendarClient, start_dt: datetime
    ) -> None:
        """Happy path: Google API returns conference data with join URL."""
        # Mock token endpoint
        respx.post("https://oauth2.googleapis.com/token").mock(
            return_value=httpx.Response(200, json=FAKE_TOKEN_RESPONSE)
        )
        # Mock calendar events endpoint
        respx.post(
            url__regex=r"https://www\.googleapis\.com/calendar/v3/calendars/.+/events"
        ).mock(return_value=httpx.Response(200, json=FAKE_GCAL_RESPONSE))

        request_id = uuid.uuid4()
        end_dt = start_dt + timedelta(hours=1)

        gcal_client._access_token = "fake_token_xyz"
        gcal_client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)

        with patch.object(gcal_client, "_get_access_token", return_value="fake_token_xyz"):
            gcal_event_id, join_url = await gcal_client.create_event(
                summary="Colab Meeting",
                start_dt=start_dt,
                end_dt=end_dt,
                attendee_emails=["a@test.com", "b@test.com"],
                request_id=request_id,
            )

        assert gcal_event_id == "event_id_123"
        assert join_url == FAKE_JOIN_URL

    @respx.mock
    async def test_create_event_idempotency_409(
        self, gcal_client: GoogleCalendarClient, start_dt: datetime
    ) -> None:
        """Stable requestId — if Google returns 409 (duplicate), we re-raise for caller."""
        respx.post(
            url__regex=r"https://www\.googleapis\.com/calendar/v3/calendars/.+/events"
        ).mock(return_value=httpx.Response(409, json={"error": {"message": "Duplicate requestId"}}))

        request_id = uuid.uuid4()
        end_dt = start_dt + timedelta(hours=1)

        with patch.object(gcal_client, "_get_access_token", return_value="fake_token_xyz"):
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await gcal_client.create_event(
                    summary="Colab Meeting",
                    start_dt=start_dt,
                    end_dt=end_dt,
                    attendee_emails=[],
                    request_id=request_id,
                )
        assert exc_info.value.response.status_code == 409

    @respx.mock
    async def test_create_event_retry_exhaustion_502(
        self, gcal_client: GoogleCalendarClient, start_dt: datetime
    ) -> None:
        """After 3 retries on 502, raises RuntimeError."""
        respx.post(
            url__regex=r"https://www\.googleapis\.com/calendar/v3/calendars/.+/events"
        ).mock(return_value=httpx.Response(502, json={"error": "Bad Gateway"}))

        request_id = uuid.uuid4()
        end_dt = start_dt + timedelta(hours=1)

        with patch.object(gcal_client, "_get_access_token", return_value="fake_token_xyz"):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(RuntimeError, match="failed after"):
                    await gcal_client.create_event(
                        summary="Colab Meeting",
                        start_dt=start_dt,
                        end_dt=end_dt,
                        attendee_emails=[],
                        request_id=request_id,
                    )

    @respx.mock
    async def test_create_event_missing_join_url(
        self, gcal_client: GoogleCalendarClient, start_dt: datetime
    ) -> None:
        """RuntimeError if conference data has no video entry point."""
        no_url_response = {
            "id": "event_id_456",
            "conferenceData": {"entryPoints": []},
        }
        respx.post(
            url__regex=r"https://www\.googleapis\.com/calendar/v3/calendars/.+/events"
        ).mock(return_value=httpx.Response(200, json=no_url_response))

        request_id = uuid.uuid4()

        with patch.object(gcal_client, "_get_access_token", return_value="fake_token_xyz"):
            with pytest.raises(RuntimeError, match="Meet join URL"):
                await gcal_client.create_event(
                    summary="Colab Meeting",
                    start_dt=start_dt,
                    end_dt=start_dt + timedelta(hours=1),
                    attendee_emails=[],
                    request_id=request_id,
                )
