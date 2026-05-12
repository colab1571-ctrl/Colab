"""
Core notification dispatch engine.

Per notification:
1. Resolve per-type per-channel preferences.
2. Apply email-fallback rule for key types.
3. Dispatch: push via SNS, email via SES, in-app via RabbitMQ.
4. Record delivery state on Notification row.
5. Idempotent via Redis SETNX on notification.id.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from botocore.exceptions import ClientError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from colab_common.settings import get_settings

from .channels.email import MARKETING_ADDRESS, send_email
from .channels.inapp import publish_inapp_banner
from .channels.push import delete_sns_endpoint, send_push
from .models import KEY_NOTIFICATION_TYPES, Notification, NotificationChannel, NotificationPreference, NotificationType, PushDevice

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None  # type: ignore[type-arg]


def _get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = aioredis.from_url(settings.redis.url, decode_responses=True)
    return _redis


async def _idempotency_check(notif_id: str) -> bool:
    """
    Return True if this notification has already been dispatched (skip).
    Uses Redis SETNX with 24h TTL.
    """
    redis = _get_redis()
    key = f"notif:dispatch:{notif_id}"
    was_set: bool = await redis.set(key, "1", ex=86400, nx=True)  # type: ignore[assignment]
    return not was_set  # True = already dispatched


async def _get_preference(
    session: AsyncSession,
    user_id: str,
    notif_type: str,
    channel: str,
) -> bool:
    """Return enabled state for a given user/type/channel. Default True if row missing."""
    stmt = select(NotificationPreference).where(
        NotificationPreference.user_id == user_id,  # type: ignore[arg-type]
        NotificationPreference.type == notif_type,  # type: ignore[arg-type]
        NotificationPreference.channel == channel,  # type: ignore[arg-type]
    )
    result = await session.execute(stmt)
    pref = result.scalar_one_or_none()
    if pref is None:
        return True  # default on (except marketing/digest, handled by seed)
    return bool(pref.enabled)


async def _get_active_push_devices(session: AsyncSession, user_id: str) -> list[PushDevice]:
    """Return active push devices for user."""
    stmt = select(PushDevice).where(
        PushDevice.user_id == user_id,  # type: ignore[arg-type]
        PushDevice.endpoint_enabled == True,  # noqa: E712
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _mark_endpoint_disabled(session: AsyncSession, device: PushDevice) -> None:
    """Mark a push device's endpoint as disabled (SNS EndpointDisabled)."""
    await session.execute(
        update(PushDevice)
        .where(PushDevice.id == device.id)
        .values(endpoint_enabled=False, sns_endpoint_arn=None)
    )


async def dispatch_notification(
    session: AsyncSession,
    notif_id: str,
    user_id: str,
    notif_type: str,
    payload: dict[str, Any],
    *,
    # Push copy
    push_title: str,
    push_body: str,
    push_deep_link: str | None = None,
    # Email copy
    email_subject: str | None = None,
    email_template: str | None = None,
    email_context: dict[str, Any] | None = None,
    email_from: str | None = None,
    # In-app copy
    inapp_title: str | None = None,
    inapp_body: str | None = None,
    inapp_action_url: str | None = None,
    # Overrides
    force_email: bool = False,  # transactional override (ignores preferences)
) -> None:
    """
    Dispatch a notification across all enabled channels.
    Idempotent: skips if already dispatched.
    """
    # --- Idempotency gate ---
    if await _idempotency_check(notif_id):
        logger.debug("Notification already dispatched, skipping", extra={"notif_id": notif_id})
        return

    now = datetime.now(tz=timezone.utc)
    notification: Notification | None = None

    # Load Notification row
    stmt = select(Notification).where(Notification.id == notif_id)  # type: ignore[arg-type]
    result = await session.execute(stmt)
    notification = result.scalar_one_or_none()
    if notification is None:
        logger.error("Notification row not found: %s", notif_id)
        return

    # --- Push channel ---
    push_enabled = await _get_preference(session, user_id, notif_type, NotificationChannel.push)
    push_delivered = False
    push_failed = False

    if push_enabled:
        devices = await _get_active_push_devices(session, user_id)
        for device in devices:
            endpoint_arn = device.sns_endpoint_arn
            if not endpoint_arn:
                continue
            try:
                send_push(
                    endpoint_arn=endpoint_arn,
                    platform=str(device.platform),
                    title=push_title,
                    body=push_body,
                    notif_id=notif_id,
                    notif_type=notif_type,
                    deep_link=push_deep_link,
                )
                push_delivered = True
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code == "EndpointDisabled":
                    await _mark_endpoint_disabled(session, device)
                    push_failed = True
                    logger.warning(
                        "SNS EndpointDisabled, disabling device",
                        extra={"device_id": str(device.device_id), "user_id": user_id},
                    )
                else:
                    push_failed = True
                    logger.error("SNS push failed: %s", code)

    # Update Notification row for push
    push_updates: dict[str, Any] = {}
    if push_delivered:
        push_updates["delivered_push_at"] = now
    elif push_failed:
        push_updates["push_failed_at"] = now
        push_updates["push_failure_reason"] = "sns_error"

    # --- Email channel ---
    email_should_send = force_email
    if not email_should_send:
        email_enabled = await _get_preference(session, user_id, notif_type, NotificationChannel.email)
        if email_enabled:
            # Direct send (preference on)
            email_should_send = True
        elif notif_type in KEY_NOTIFICATION_TYPES:
            # Fallback: push unreachable → send email for key types
            push_devices = await _get_active_push_devices(session, user_id)
            push_unreachable = not push_enabled or not push_devices or push_failed
            if push_unreachable:
                # Check if fallback email is enabled
                fallback_email_enabled = await _get_preference(session, user_id, notif_type, NotificationChannel.email)
                if fallback_email_enabled:
                    email_should_send = True

    email_updates: dict[str, Any] = {}
    if email_should_send and email_template and email_subject:
        ctx = email_context or {}
        from_addr = email_from or MARKETING_ADDRESS if notif_type == NotificationType.marketing else None
        success = send_email(
            to_address=payload.get("recipient_email", ""),
            subject=email_subject,
            template_name=email_template,
            context=ctx,
            **({"from_address": from_addr} if from_addr else {}),
        )
        if success:
            email_updates["delivered_email_at"] = now
        else:
            email_updates["email_failed_at"] = now
            email_updates["email_failure_reason"] = "ses_error"

    # --- In-app channel ---
    inapp_enabled = await _get_preference(session, user_id, notif_type, NotificationChannel.in_app)
    if inapp_enabled and inapp_title and inapp_body:
        await publish_inapp_banner(
            user_id=user_id,
            notif_id=notif_id,
            notif_type=notif_type,
            title=inapp_title,
            body=inapp_body,
            action_url=inapp_action_url,
            created_at=now,
        )

    # --- Persist delivery state ---
    all_updates = {**push_updates, **email_updates}
    if all_updates:
        await session.execute(
            update(Notification).where(Notification.id == notif_id).values(**all_updates)  # type: ignore[arg-type]
        )
