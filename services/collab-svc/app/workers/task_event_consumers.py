"""
Celery consumers (async event handlers) that relay task events as system
messages into chat-svc.

Event routing:
  task.created          → "@{actor} added task \"{title}\""
  task.status_changed   → "@{actor} moved \"{title}\" to {status_label}"
  task.assigned         → "@{actor} assigned \"{title}\" to @{assignee}"
  task.deleted          → "@{actor} deleted task \"{title}\""

These handlers are called from RabbitMQ message consumers, NOT from Celery
directly — they are async coroutines invoked via asyncio.run() inside the
Celery task wrapper below.

chat-svc must expose: POST /internal/rooms/{room_id}/system-message
  body: {body: str, metadata: dict}

The chat_room_id is resolved by looking up the Collaboration.chat_room_id.
Since collab-svc doesn't store chat_room_id (chat-svc owns ChatRoom), we
call chat-svc's internal lookup endpoint to resolve room by collab_id.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

TASK_STATUS_LABELS: dict[str, str] = {
    "todo": "To Do",
    "in_progress": "In Progress",
    "done": "Done",
    "blocked": "Blocked",
}


# ---------------------------------------------------------------------------
# Celery tasks (sync wrapper around async logic)
# ---------------------------------------------------------------------------


@celery_app.task(
    name="task_events.dispatch_system_message",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def dispatch_task_system_message(self, event_type: str, payload: dict[str, Any]) -> None:
    """
    Generic Celery task to dispatch a task event as a system message into chat.
    Called by the RabbitMQ consumer after each task.* event is received.
    """
    try:
        asyncio.run(_async_dispatch(event_type, payload))
    except Exception as exc:
        logger.error("dispatch_task_system_message failed: %s", exc)
        raise self.retry(exc=exc)


async def _async_dispatch(event_type: str, payload: dict[str, Any]) -> None:
    collab_id_str = payload.get("collab_id")
    if not collab_id_str:
        logger.warning("No collab_id in task event payload: %s", payload)
        return

    collab_id = uuid.UUID(collab_id_str)
    body = _build_system_message(event_type, payload)
    if body is None:
        return

    # Resolve chat_room_id via chat-svc internal endpoint
    chat_room_id = await _resolve_chat_room(collab_id)
    if chat_room_id is None:
        logger.warning("Could not resolve chat_room_id for collab %s", collab_id)
        return

    from app.services.chat_client import post_system_message

    await post_system_message(
        chat_room_id=chat_room_id,
        body=body,
        metadata={
            "event": event_type,
            "collab_id": collab_id_str,
            "task_id": payload.get("task_id"),
            "actor_id": payload.get("actor_profile_id"),
            **_extra_metadata(event_type, payload),
        },
    )


def _build_system_message(event_type: str, payload: dict[str, Any]) -> str | None:
    actor = payload.get("actor_display_name") or f"@{payload.get('actor_profile_id', 'Unknown')[:8]}"
    title = payload.get("task_title", "(untitled)")

    if event_type == "task.created":
        return f"{actor} added task \"{title}\""
    if event_type == "task.status_changed":
        new_status = payload.get("new_status", "")
        label = TASK_STATUS_LABELS.get(new_status, new_status.replace("_", " ").title())
        return f"{actor} moved \"{title}\" to {label}"
    if event_type == "task.assigned":
        assignee = payload.get("assignee_display_name") or f"@{payload.get('assignee_profile_id', 'Unknown')[:8]}"
        return f"{actor} assigned \"{title}\" to {assignee}"
    if event_type == "task.deleted":
        return f"{actor} deleted task \"{title}\""
    return None


def _extra_metadata(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if event_type == "task.status_changed":
        return {
            "prev_status": payload.get("prev_status"),
            "new_status": payload.get("new_status"),
        }
    if event_type == "task.assigned":
        return {"assignee_profile_id": payload.get("assignee_profile_id")}
    return {}


async def _resolve_chat_room(collab_id: uuid.UUID) -> uuid.UUID | None:
    """
    Ask chat-svc for the chat room associated with this collab.
    chat-svc exposes GET /internal/rooms/by-collab/{collab_id}.
    """
    from app.config import get_collab_settings

    import httpx

    settings = get_collab_settings()
    url = f"{settings.chat_svc_url}/internal/rooms/by-collab/{collab_id}"
    headers = {"X-Service-Secret": settings.service_shared_secret}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return uuid.UUID(data["room_id"])
            return None
    except Exception as exc:
        logger.error("Failed to resolve chat room for collab %s: %s", collab_id, exc)
        return None
