"""
GoogleCalendarClient — wraps Google Calendar API v3 for meeting creation.

Uses a service account (domain-wide delegation pattern) loaded from
Secrets Manager. The JSON key is passed via env var MEETING_GOOGLE_SERVICE_ACCOUNT_JSON.

Methods:
- create_event(...)   → (gcal_event_id, join_url)
- patch_event(...)    → None
- delete_event(...)   → None (soft-delete; we generally do not delete)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
TOKEN_URL = "https://oauth2.googleapis.com/token"

_MAX_RETRIES = 3
_RETRY_STATUSES = {429, 500, 502, 503, 504}


def _build_jwt_assertion(service_account_info: dict[str, Any]) -> str:
    """Build a signed JWT assertion for Google OAuth2 service account token exchange."""
    import base64
    import json as _json
    import time

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        private_key_pem = service_account_info["private_key"].encode()
        private_key = serialization.load_pem_private_key(private_key_pem, password=None)

        now = int(time.time())
        header = {"alg": "RS256", "typ": "JWT"}
        payload = {
            "iss": service_account_info["client_email"],
            "scope": CALENDAR_SCOPE,
            "aud": TOKEN_URL,
            "iat": now,
            "exp": now + 3600,
        }

        def _b64(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        header_b64 = _b64(_json.dumps(header).encode())
        payload_b64 = _b64(_json.dumps(payload).encode())
        signing_input = f"{header_b64}.{payload_b64}".encode()

        signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        sig_b64 = _b64(signature)

        return f"{header_b64}.{payload_b64}.{sig_b64}"
    except ImportError:
        # cryptography not installed — raise for ops to fix
        raise RuntimeError(
            "cryptography package required for service account JWT signing. "
            "Install: pip install cryptography"
        )


class GoogleCalendarClient:
    """Async Google Calendar API v3 client using service account credentials."""

    def __init__(self, service_account_json: str, calendar_id: str = "primary") -> None:
        self._service_account_info: dict[str, Any] = json.loads(service_account_json)
        self._calendar_id = calendar_id
        self._access_token: str | None = None
        self._token_expires_at: datetime = datetime.now(UTC)

    async def _get_access_token(self) -> str:
        """Obtain or refresh an access token using JWT assertion flow."""
        now = datetime.now(UTC)
        if self._access_token and now < self._token_expires_at - timedelta(seconds=60):
            return self._access_token

        jwt_assertion = _build_jwt_assertion(self._service_account_info)

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": jwt_assertion,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expires_at = now + timedelta(seconds=data.get("expires_in", 3600))
            return self._access_token

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an authenticated request with retry on transient errors."""
        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.request(
                        method,
                        f"{CALENDAR_API_BASE}{path}",
                        headers=headers,
                        **kwargs,
                    )
                    if resp.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES - 1:
                        wait = 2 ** attempt
                        logger.warning(
                            "Google Calendar API %s %s → %d, retry in %ds",
                            method, path, resp.status_code, wait,
                        )
                        import asyncio
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in _RETRY_STATUSES:
                    raise
            except httpx.RequestError as exc:
                last_exc = exc
                import asyncio
                await asyncio.sleep(2 ** attempt)

        raise RuntimeError(
            f"Google Calendar API failed after {_MAX_RETRIES} attempts"
        ) from last_exc

    async def create_event(
        self,
        *,
        summary: str,
        start_dt: datetime,
        end_dt: datetime,
        attendee_emails: list[str],
        request_id: uuid.UUID,
    ) -> tuple[str, str]:
        """
        Create a Google Calendar event with Meet conference data.

        Returns (gcal_event_id, join_url).
        Raises RuntimeError on exhausted retries → caller returns 502.
        """
        body = {
            "summary": summary,
            "start": {"dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "timeZone": "UTC"},
            "end": {"dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "timeZone": "UTC"},
            "attendees": [{"email": e} for e in attendee_emails],
            "conferenceData": {
                "createRequest": {
                    "requestId": str(request_id),
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }

        data = await self._request(
            "POST",
            f"/calendars/{self._calendar_id}/events",
            params={"conferenceDataVersion": "1"},
            json=body,
        )

        gcal_event_id: str = data["id"]
        entry_points = (
            data.get("conferenceData", {}).get("entryPoints", [])
        )
        join_url = next(
            (ep["uri"] for ep in entry_points if ep.get("entryPointType") == "video"),
            "",
        )

        if not join_url:
            logger.error("No Meet join URL in Google Calendar response: %s", data)
            raise RuntimeError("Google Calendar did not return a Meet join URL")

        logger.info("Created GCal event %s → %s", gcal_event_id, join_url)
        return gcal_event_id, join_url

    async def patch_event(
        self,
        event_id: str,
        *,
        start_dt: datetime,
        end_dt: datetime,
    ) -> None:
        """Reschedule an existing calendar event."""
        body = {
            "start": {"dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "timeZone": "UTC"},
            "end": {"dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "timeZone": "UTC"},
        }
        await self._request(
            "PATCH",
            f"/calendars/{self._calendar_id}/events/{event_id}",
            json=body,
        )
        logger.info("Patched GCal event %s", event_id)

    async def delete_event(self, event_id: str) -> None:
        """Delete a calendar event (used for hard-cancel cleanup if needed)."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                token = await self._get_access_token()
                resp = await client.delete(
                    f"{CALENDAR_API_BASE}/calendars/{self._calendar_id}/events/{event_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code not in (200, 204, 410):
                    resp.raise_for_status()
        except Exception as exc:
            logger.warning("GCal delete_event %s failed: %s", event_id, exc)
