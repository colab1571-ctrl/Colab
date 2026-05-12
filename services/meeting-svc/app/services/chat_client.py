"""
chat-svc internal API client — posts system messages for meeting events.

The meeting-svc calls chat-svc internal REST endpoint (not via gateway)
using the service-to-service shared secret.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ChatSvcClient:
    """Minimal client for posting system messages to chat-svc."""

    def __init__(self, base_url: str, shared_secret: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._shared_secret = shared_secret

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._shared_secret}",
            "Content-Type": "application/json",
            "X-Internal-Service": "meeting-svc",
        }

    async def post_transcript_system_message(
        self,
        *,
        collab_id: uuid.UUID,
        meeting_id: uuid.UUID,
        scheduled_at: datetime,
    ) -> None:
        """
        Create a system|transcript ChatMessage in the collab chat room.

        The message is collapsible; the client fetches transcript content
        via GET /meetings/{id}/artifacts/{artifact_id}/download.
        """
        payload: dict[str, Any] = {
            "type": "system",
            "subtype": "transcript",
            "content": "Meeting transcript is ready.",
            "metadata": {
                "meeting_id": str(meeting_id),
                "meeting_scheduled_at": scheduled_at.isoformat(),
                "artifact_kind": "transcript",
                "collapse": True,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self._base_url}/internal/collabs/{collab_id}/messages",
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                logger.info(
                    "Posted transcript system message to collab %s for meeting %s",
                    collab_id,
                    meeting_id,
                )
        except Exception as exc:
            # Non-fatal: the queue event will also trigger chat-svc consumer.
            # Log and continue — do not fail transcript ingestion.
            logger.warning(
                "Failed to post transcript system message to chat-svc: %s", exc
            )
