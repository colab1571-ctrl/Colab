"""
Push device registration API router.

Endpoints:
  POST   /devices/push
  DELETE /devices/push/{device_id}
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from colab_common.auth import AuthUser, require_user
from colab_common.db import get_session

from ..channels.push import create_or_update_sns_endpoint, delete_sns_endpoint
from ..models import Notification, NotificationType, PushDevice
from ..schemas import RegisterDeviceRequest, RegisterDeviceResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["devices"])

# Notification types that are NOT marketing/digest (for pre-permission check)
_PROMPTABLE_TYPES = {t.value for t in NotificationType} - {
    NotificationType.marketing.value,
    NotificationType.weekly_digest.value,
}


async def _has_queued_notifications(session: AsyncSession, user_id: str) -> int:
    """Return count of undelivered non-marketing notifications for the user."""
    stmt = select(Notification).where(
        Notification.user_id == user_id,  # type: ignore[arg-type]
        Notification.delivered_push_at.is_(None),
        Notification.push_failed_at.is_(None),
        Notification.type.in_(_PROMPTABLE_TYPES),  # type: ignore[arg-type]
    )
    result = await session.execute(stmt)
    return len(result.scalars().all())


async def _user_has_active_token(session: AsyncSession, user_id: str) -> bool:
    """Return True if user has any active push device with a registered token."""
    stmt = select(PushDevice).where(
        PushDevice.user_id == user_id,  # type: ignore[arg-type]
        PushDevice.endpoint_enabled == True,  # noqa: E712
    )
    result = await session.execute(stmt)
    devices = result.scalars().all()
    return any(d.sns_endpoint_arn or d.expo_push_token for d in devices)


@router.post("/devices/push", response_model=RegisterDeviceResponse)
async def register_push_device(
    body: RegisterDeviceRequest,
    auth_user: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> RegisterDeviceResponse:
    user_id = auth_user.user_id
    # Get or create PushDevice row
    stmt = select(PushDevice).where(
        PushDevice.user_id == user_id,  # type: ignore[arg-type]
        PushDevice.device_id == body.device_id,
    )
    result = await session.execute(stmt)
    device = result.scalar_one_or_none()

    now = datetime.now(tz=timezone.utc)

    if device is None:
        device = PushDevice(
            user_id=user_id,  # type: ignore[arg-type]
            device_id=body.device_id,
            platform=body.platform,
            expo_push_token=body.expo_push_token,
            device_token=body.device_token,
            app_version=body.app_version,
            os_version=body.os_version,
            last_seen_at=now,
        )
        session.add(device)
        await session.flush()
    else:
        device.last_seen_at = now  # type: ignore[assignment]
        if body.app_version:
            device.app_version = body.app_version  # type: ignore[assignment]
        if body.os_version:
            device.os_version = body.os_version  # type: ignore[assignment]

    # SNS endpoint creation (prod path: device_token present)
    if body.device_token and not device.sns_endpoint_arn:
        endpoint_arn = create_or_update_sns_endpoint(
            device_token=body.device_token,
            platform=body.platform,
            user_id=user_id,
        )
        if endpoint_arn:
            device.sns_endpoint_arn = endpoint_arn  # type: ignore[assignment]
            device.device_token = body.device_token  # type: ignore[assignment]
            device.endpoint_enabled = True  # type: ignore[assignment]

    # Dev path: expo token
    if body.expo_push_token:
        device.expo_push_token = body.expo_push_token  # type: ignore[assignment]

    # Pre-permission prompt logic
    has_token = bool(device.sns_endpoint_arn or device.expo_push_token)
    queued_count = await _has_queued_notifications(session, user_id) if not has_token else 0
    has_queued = queued_count > 0

    should_prompt = not has_token and has_queued

    # Track dismissal count — threshold 3 suppresses forever
    if should_prompt:
        dismissed = int(device.prompt_dismissed_count or "0")
        if dismissed >= 3:
            should_prompt = False

    return RegisterDeviceResponse(
        device_id=body.device_id,
        registered=has_token,
        should_prompt_push=should_prompt,
        queued_count=queued_count if should_prompt else 0,
    )


@router.delete("/devices/push/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deregister_push_device(
    device_id: str,
    auth_user: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    user_id = auth_user.user_id
    stmt = select(PushDevice).where(
        PushDevice.user_id == user_id,  # type: ignore[arg-type]
        PushDevice.device_id == device_id,
    )
    result = await session.execute(stmt)
    device = result.scalar_one_or_none()

    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    endpoint_arn = device.sns_endpoint_arn
    await session.delete(device)

    if endpoint_arn:
        delete_sns_endpoint(endpoint_arn)
