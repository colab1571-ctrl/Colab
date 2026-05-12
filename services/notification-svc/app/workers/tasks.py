"""
Celery tasks for notification dispatch — one task per notification type.

Each task:
1. Creates a Notification row.
2. Calls dispatch_notification() for full channel routing.
3. Handles idempotency via Redis SETNX on event-specific key.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import redis
from celery import shared_task

from colab_common.db import session_scope
from colab_common.settings import get_settings

from ..dispatch import dispatch_notification
from ..models import Notification, NotificationType

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _get_sync_redis() -> redis.Redis:  # type: ignore[type-arg]
    settings = get_settings()
    return redis.from_url(settings.redis.url, decode_responses=True)


def _idempotency_setnx(key: str, ttl: int = 3600) -> bool:
    """Return True if we should proceed (key was newly set), False if duplicate."""
    r = _get_sync_redis()
    return bool(r.set(key, "1", ex=ttl, nx=True))


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _create_and_dispatch(
    user_id: str,
    notif_type: str,
    payload: dict[str, Any],
    **dispatch_kwargs: Any,
) -> None:
    """Create Notification row and dispatch in one DB session."""
    async with session_scope() as session:
        notif = Notification(
            user_id=user_id,  # type: ignore[arg-type]
            type=notif_type,  # type: ignore[arg-type]
            payload=payload,
        )
        session.add(notif)
        await session.flush()
        notif_id = str(notif.id)

        await dispatch_notification(
            session=session,
            notif_id=notif_id,
            user_id=user_id,
            notif_type=notif_type,
            payload=payload,
            **dispatch_kwargs,
        )


# --------------------------------------------------------------------------
# Task: new_match (match.created → both users)
# --------------------------------------------------------------------------


@shared_task(bind=True, max_retries=3, default_retry_delay=2, name="notification.new_match")
def task_new_match(self: Any, user_id: str, other_user_display_name: str, collab_id: str, match_id: str, **kwargs: Any) -> None:
    key = f"notif:idem:new_match:{match_id}:{user_id}"
    if not _idempotency_setnx(key, ttl=30):
        return

    payload = {
        "match_id": match_id,
        "other_user_display_name": other_user_display_name,
        "collab_id": collab_id,
        **kwargs,
    }

    try:
        _run_async(
            _create_and_dispatch(
                user_id=user_id,
                notif_type=NotificationType.new_match,
                payload=payload,
                push_title=f"You matched with {other_user_display_name}!",
                push_body="Start your collaboration now.",
                push_deep_link=f"/collabs/{collab_id}",
                email_subject="You have a new match on Colab!",
                email_template="new_match.html",
                email_context=payload,
                inapp_title="New Match!",
                inapp_body=f"You matched with {other_user_display_name}! Tap to open your workspace.",
                inapp_action_url=f"/collabs/{collab_id}",
            )
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries) from exc


# --------------------------------------------------------------------------
# Task: new_request (invite.sent → recipient)
# --------------------------------------------------------------------------


@shared_task(bind=True, max_retries=3, default_retry_delay=2, name="notification.new_request")
def task_new_request(self: Any, user_id: str, sender_display_name: str, synopsis: str, invite_id: str, **kwargs: Any) -> None:
    payload = {"invite_id": invite_id, "sender_display_name": sender_display_name, "synopsis": synopsis, **kwargs}
    synopsis_truncated = synopsis[:100] if len(synopsis) > 100 else synopsis

    try:
        _run_async(
            _create_and_dispatch(
                user_id=user_id,
                notif_type=NotificationType.new_request,
                payload=payload,
                push_title=f"{sender_display_name} sent you a Vibe Check",
                push_body=synopsis_truncated,
                email_subject=f"{sender_display_name} wants to collaborate with you",
                email_template="new_request.html",
                email_context=payload,
                inapp_title="New Vibe Check",
                inapp_body=f"New Vibe Check from {sender_display_name}",
            )
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries) from exc


# --------------------------------------------------------------------------
# Task: request_accepted (invite.accepted → original sender)
# --------------------------------------------------------------------------


@shared_task(bind=True, max_retries=3, default_retry_delay=2, name="notification.request_accepted")
def task_request_accepted(self: Any, user_id: str, acceptor_display_name: str, collab_id: str, **kwargs: Any) -> None:
    payload = {"acceptor_display_name": acceptor_display_name, "collab_id": collab_id, **kwargs}

    try:
        _run_async(
            _create_and_dispatch(
                user_id=user_id,
                notif_type=NotificationType.request_accepted,
                payload=payload,
                push_title=f"{acceptor_display_name} accepted your Vibe Check!",
                push_body="Your collaboration workspace is ready.",
                push_deep_link=f"/collabs/{collab_id}",
                email_subject="Your Vibe Check was accepted — time to create!",
                email_template="request_accepted.html",
                email_context=payload,
                inapp_title="Vibe Check Accepted",
                inapp_body=f"{acceptor_display_name} accepted your Vibe Check! Open workspace",
                inapp_action_url=f"/collabs/{collab_id}",
            )
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries) from exc


# --------------------------------------------------------------------------
# Task: chat_message (chat.message.sent → recipient, with debounce)
# --------------------------------------------------------------------------


@shared_task(bind=True, max_retries=3, default_retry_delay=2, name="notification.chat_message")
def task_chat_message(
    self: Any,
    user_id: str,
    sender_display_name: str,
    message_preview: str,
    message_type: str,
    collab_id: str,
    **kwargs: Any,
) -> None:
    # Debounce: check Redis presence key
    r = _get_sync_redis()
    presence_key = f"presence:{user_id}"
    chat_active_key = f"chat_active:{user_id}:{collab_id}"

    if r.exists(presence_key) and r.exists(chat_active_key):
        # User is in the room — suppress push for 60s debounce window
        debounce_key = f"notif:debounce:chat:{user_id}:{collab_id}"
        if not _idempotency_setnx(debounce_key, ttl=60):
            logger.debug("Chat message debounced for user %s collab %s", user_id, collab_id)
            return

    body_map = {"voice": "Sent a voice note", "file": "Sent a file"}
    push_body = body_map.get(message_type, message_preview)
    payload = {
        "sender_display_name": sender_display_name,
        "message_preview": message_preview,
        "collab_id": collab_id,
        "message_type": message_type,
        **kwargs,
    }

    try:
        _run_async(
            _create_and_dispatch(
                user_id=user_id,
                notif_type=NotificationType.chat_message,
                payload=payload,
                push_title=sender_display_name,
                push_body=push_body,
                push_deep_link=f"/collabs/{collab_id}/chat",
                # email is OFF by default for chat_message
                inapp_title=sender_display_name,
                inapp_body=f"{sender_display_name}: {message_preview}",
                inapp_action_url=f"/collabs/{collab_id}/chat",
            )
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries) from exc


# --------------------------------------------------------------------------
# Task: file_shared
# --------------------------------------------------------------------------


@shared_task(bind=True, max_retries=3, default_retry_delay=2, name="notification.file_shared")
def task_file_shared(
    self: Any,
    user_id: str,
    sender_display_name: str,
    file_name: str,
    file_type: str,
    collab_id: str,
    **kwargs: Any,
) -> None:
    payload = {
        "sender_display_name": sender_display_name,
        "file_name": file_name,
        "file_type": file_type,
        "collab_id": collab_id,
        **kwargs,
    }
    try:
        _run_async(
            _create_and_dispatch(
                user_id=user_id,
                notif_type=NotificationType.file_shared,
                payload=payload,
                push_title=f"{sender_display_name} shared a file",
                push_body=f"{file_name} ({file_type})",
                push_deep_link=f"/collabs/{collab_id}/chat",
                inapp_title="File Shared",
                inapp_body=f"{sender_display_name} shared {file_name}",
                inapp_action_url=f"/collabs/{collab_id}/chat",
            )
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries) from exc


# --------------------------------------------------------------------------
# Task: ai_mockup_ready (urgency override — always push + email)
# --------------------------------------------------------------------------


@shared_task(bind=True, max_retries=3, default_retry_delay=2, name="notification.ai_mockup_ready")
def task_ai_mockup_ready(
    self: Any,
    user_id: str,
    collab_id: str,
    mockup_id: str,
    expires_at: str,
    mockup_type: str = "image",
    **kwargs: Any,
) -> None:
    payload = {
        "collab_id": collab_id,
        "mockup_id": mockup_id,
        "expires_at": expires_at,
        "mockup_type": mockup_type,
        **kwargs,
    }
    try:
        _run_async(
            _create_and_dispatch(
                user_id=user_id,
                notif_type=NotificationType.ai_mockup_ready,
                payload=payload,
                push_title="Your AI Collab Preview is ready!",
                push_body=f"Tap to view before it expires.",
                push_deep_link=f"/collabs/{collab_id}/mockup/{mockup_id}",
                email_subject=f"Your AI Collab Preview is ready",
                email_template="ai_mockup_ready.html",
                email_context=payload,
                inapp_title="AI Preview Ready",
                inapp_body="AI Collab Preview ready! View before it expires.",
                inapp_action_url=f"/collabs/{collab_id}/mockup/{mockup_id}",
            )
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries) from exc


# --------------------------------------------------------------------------
# Task: collab_nudge
# --------------------------------------------------------------------------


@shared_task(bind=True, max_retries=3, default_retry_delay=2, name="notification.collab_nudge")
def task_collab_nudge(
    self: Any,
    user_id: str,
    collab_id: str,
    other_user_display_name: str,
    inactive_days: int,
    nudge_cycle_date: str,
    auto_archive_at: str,
    **kwargs: Any,
) -> None:
    key = f"notif:idem:nudge:{collab_id}:{nudge_cycle_date}:{user_id}"
    if not _idempotency_setnx(key, ttl=172800):  # 48h TTL
        return

    payload = {
        "collab_id": collab_id,
        "other_user_display_name": other_user_display_name,
        "inactive_days": inactive_days,
        "auto_archive_at": auto_archive_at,
        **kwargs,
    }
    try:
        _run_async(
            _create_and_dispatch(
                user_id=user_id,
                notif_type=NotificationType.collab_nudge,
                payload=payload,
                push_title=f"Your collab with {other_user_display_name} is going quiet",
                push_body=f"No activity in {inactive_days} days. Say something before it archives.",
                push_deep_link=f"/collabs/{collab_id}",
                email_subject=f"Your collaboration with {other_user_display_name} needs attention",
                email_template="collab_nudge.html",
                email_context=payload,
                inapp_title="Collab Nudge",
                inapp_body=f"{other_user_display_name} collab is inactive — say something before it archives.",
                inapp_action_url=f"/collabs/{collab_id}",
            )
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries) from exc


# --------------------------------------------------------------------------
# Task: collab_status_change
# --------------------------------------------------------------------------


@shared_task(bind=True, max_retries=3, default_retry_delay=2, name="notification.collab_status_change")
def task_collab_status_change(
    self: Any,
    user_id: str,
    collab_id: str,
    other_user_display_name: str,
    new_status: str,
    **kwargs: Any,
) -> None:
    push_title_map = {
        "in_progress": f"{other_user_display_name} marked your collab as In Progress",
        "completed": f"Collab with {other_user_display_name} marked Completed. Share your feedback!",
        "didnt_work_out": f"Collab with {other_user_display_name} has ended.",
    }
    push_title = push_title_map.get(new_status, "Collab status updated")
    payload = {
        "collab_id": collab_id,
        "other_user_display_name": other_user_display_name,
        "new_status": new_status,
        **kwargs,
    }

    email_template = None
    email_subject = None
    if new_status == "completed":
        email_template = "collab_completed.html"
        email_subject = "Congrats! Your collaboration is complete — leave feedback"

    try:
        _run_async(
            _create_and_dispatch(
                user_id=user_id,
                notif_type=NotificationType.collab_status_change,
                payload=payload,
                push_title=push_title,
                push_body=push_title,
                push_deep_link=f"/collabs/{collab_id}",
                email_subject=email_subject,
                email_template=email_template,
                email_context=payload,
                inapp_title="Collab Update",
                inapp_body=push_title,
                inapp_action_url=f"/collabs/{collab_id}",
            )
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries) from exc


# --------------------------------------------------------------------------
# Task: support_reply
# --------------------------------------------------------------------------


@shared_task(bind=True, max_retries=3, default_retry_delay=2, name="notification.support_reply")
def task_support_reply(
    self: Any,
    user_id: str,
    ticket_id: str,
    ticket_subject: str,
    reply_preview: str,
    **kwargs: Any,
) -> None:
    payload = {
        "ticket_id": ticket_id,
        "ticket_subject": ticket_subject,
        "reply_preview": reply_preview,
        **kwargs,
    }
    try:
        _run_async(
            _create_and_dispatch(
                user_id=user_id,
                notif_type=NotificationType.support_reply,
                payload=payload,
                push_title="Update on your support request",
                push_body=reply_preview,
                push_deep_link=f"/support/tickets/{ticket_id}",
                email_subject=f"Re: {ticket_subject}",
                email_template="support_reply.html",
                email_context=payload,
                inapp_title="Support Update",
                inapp_body=f"Support replied: {reply_preview}",
                inapp_action_url=f"/support/tickets/{ticket_id}",
            )
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries) from exc


# --------------------------------------------------------------------------
# Task: marketing broadcast (fan-out is handled by consumer)
# --------------------------------------------------------------------------


@shared_task(bind=True, max_retries=3, default_retry_delay=2, name="notification.marketing")
def task_marketing(
    self: Any,
    user_id: str,
    campaign_id: str,
    title: str,
    body: str,
    action_url: str | None = None,
    **kwargs: Any,
) -> None:
    # Throttle: max 1 per user per 24h
    throttle_key = f"notif:throttle:marketing:{user_id}"
    if not _idempotency_setnx(throttle_key, ttl=86400):
        logger.debug("Marketing throttled for user %s", user_id)
        return

    payload = {"campaign_id": campaign_id, "title": title, "body": body, "action_url": action_url}
    try:
        _run_async(
            _create_and_dispatch(
                user_id=user_id,
                notif_type=NotificationType.marketing,
                payload=payload,
                push_title=title,
                push_body=body,
                email_subject=title,
                email_template="marketing.html",
                email_context=payload,
                inapp_title=title,
                inapp_body=body,
                inapp_action_url=action_url,
            )
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries) from exc
