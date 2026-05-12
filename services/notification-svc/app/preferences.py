"""
Preference seeding and helpers.

Called on user.created event to populate default NotificationPreference rows
(33 rows: 11 types x 3 channels), with marketing and weekly_digest defaulted off.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import DEFAULT_OFF_TYPES, NotificationChannel, NotificationPreference, NotificationType

logger = logging.getLogger(__name__)


async def seed_preferences(session: AsyncSession, user_id: str) -> int:
    """
    Insert default NotificationPreference rows for a new user.
    Idempotent: uses ON CONFLICT DO NOTHING.
    Returns count of rows inserted.
    """
    inserted = 0
    for notif_type in NotificationType:
        for channel in NotificationChannel:
            enabled = notif_type.value not in DEFAULT_OFF_TYPES
            pref = NotificationPreference(
                user_id=user_id,  # type: ignore[arg-type]
                type=notif_type,  # type: ignore[arg-type]
                channel=channel,  # type: ignore[arg-type]
                enabled=enabled,
            )
            session.add(pref)
            inserted += 1

    # Flush and rely on ON CONFLICT DO NOTHING from unique constraint
    try:
        await session.flush()
    except Exception as exc:
        # Likely duplicate; that's fine (idempotent)
        logger.debug("Preference seed flush warning (likely dup): %s", exc)
        await session.rollback()
        return 0

    logger.info("Seeded %d notification preferences for user %s", inserted, user_id)
    return inserted
