"""
RecallClient — wraps the Recall.ai REST API for bot management.

Base URL: https://api.recall.ai/api/v1/
Auth: Authorization: Token <RECALL_API_KEY>

Methods:
- create_bot(meeting_url, webhook_url) → recall_bot_id
- get_bot_status(bot_id) → str (status code)

Implements retry with exponential backoff on 429/503.
Circuit breaker: after 3 consecutive failures, raises RecallCircuitOpen.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_CIRCUIT_THRESHOLD = 3  # consecutive failures before circuit opens


class RecallCircuitOpen(Exception):
    """Raised when the Recall.ai circuit breaker is open."""


class RecallClient:
    """Async Recall.ai API client."""

    def __init__(self, api_key: str, base_url: str, bot_name: str = "Colab Notes Bot") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._bot_name = bot_name
        self._failure_count: int = 0
        self._circuit_open: bool = False

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Token {self._api_key}",
            "Content-Type": "application/json",
        }

    def _record_success(self) -> None:
        self._failure_count = 0
        self._circuit_open = False

    def _record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= _CIRCUIT_THRESHOLD:
            self._circuit_open = True
            logger.error(
                "Recall.ai circuit breaker OPEN after %d consecutive failures",
                self._failure_count,
            )

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if self._circuit_open:
            raise RecallCircuitOpen(
                "Recall.ai circuit breaker is open — too many consecutive failures"
            )

        url = f"{self._base_url}/{path.lstrip('/')}"
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.request(
                        method, url, headers=self._headers(), **kwargs
                    )
                    if resp.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES - 1:
                        jitter = 0.5 * attempt
                        wait = (2 ** attempt) + jitter
                        logger.warning(
                            "Recall.ai %s %s → %d, retry in %.1fs",
                            method, path, resp.status_code, wait,
                        )
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    self._record_success()
                    return resp.json()
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in _RETRY_STATUSES:
                    self._record_failure()
                    raise
                await asyncio.sleep(2 ** attempt)
            except httpx.RequestError as exc:
                last_exc = exc
                await asyncio.sleep(2 ** attempt)

        self._record_failure()
        raise RuntimeError(
            f"Recall.ai API failed after {_MAX_RETRIES} attempts"
        ) from last_exc

    async def create_bot(self, meeting_url: str, webhook_url: str) -> str:
        """
        Dispatch a Recall.ai bot to the given meeting URL.

        Returns the Recall bot ID string.
        """
        body = {
            "meeting_url": meeting_url,
            "bot_name": self._bot_name,
            "transcription_options": {"provider": "assembly_ai"},
            "recording_mode": "speaker_view",
            "webhook_url": webhook_url,
        }
        data = await self._request("POST", "/bot/", json=body)
        bot_id: str = data["id"]
        logger.info("Recall.ai bot created: %s for meeting %s", bot_id, meeting_url)
        return bot_id

    async def get_bot_status(self, bot_id: str) -> str:
        """Return the current status code of a Recall.ai bot."""
        data = await self._request("GET", f"/bot/{bot_id}/")
        return data.get("status", {}).get("code", "unknown")
