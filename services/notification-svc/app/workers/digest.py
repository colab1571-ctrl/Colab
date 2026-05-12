"""
Weekly digest Celery Beat job.

Runs every Monday at 09:00 UTC (approximation; user timezone support is v1.1).
Skips users with zero activity in the period.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from celery import shared_task
from celery.schedules import crontab
from sqlalchemy import select, text

from colab_common.db import session_scope

from ..channels.email import send_email
from ..models import NotificationChannel, NotificationPreference, NotificationType

logger = logging.getLogger(__name__)

# Register beat schedule
from .celery_app import celery_app

celery_app.conf.beat_schedule = {
    "weekly-digest": {
        "task": "notification.weekly_digest",
        "schedule": crontab(hour=9, minute=0, day_of_week=1),  # Monday 09:00 UTC
    }
}


@shared_task(bind=True, max_retries=1, name="notification.weekly_digest")
def task_weekly_digest(self: Any) -> None:  # type: ignore[name-defined]
    asyncio.new_event_loop().run_until_complete(_run_digest())


async def _run_digest() -> None:
    now = datetime.now(tz=timezone.utc)
    period_end = now
    period_start = now - timedelta(days=7)

    async with session_scope() as session:
        # Get users who opted into weekly_digest email
        stmt = select(NotificationPreference).where(
            NotificationPreference.type == NotificationType.weekly_digest,
            NotificationPreference.channel == NotificationChannel.email,
            NotificationPreference.enabled == True,  # noqa: E712
        )
        result = await session.execute(stmt)
        prefs = result.scalars().all()

        for pref in prefs:
            user_id = str(pref.user_id)
            # Fetch activity stats (stubbed — real impl joins notification/chat/match tables)
            stats = await _get_user_activity(session, user_id, period_start, period_end)
            if _is_zero_activity(stats):
                logger.debug("Skipping zero-activity user %s for digest", user_id)
                continue

            # Fetch user email (in production: call auth-svc or profile-svc via HTTP)
            user_email = await _get_user_email(session, user_id)
            if not user_email:
                continue

            context = {
                "period_start": period_start.date().isoformat(),
                "period_end": period_end.date().isoformat(),
                "period_start_formatted": period_start.strftime("%b %d"),
                **stats,
            }
            send_email(
                to_address=user_email,
                subject=f"Your Colab week in review — {context['period_start_formatted']}",
                template_name="weekly_digest.html",
                context=context,
            )
            logger.info("Weekly digest sent to user %s", user_id)


async def _get_user_activity(session: Any, user_id: str, start: datetime, end: datetime) -> dict[str, int]:
    """
    Return activity stats for the digest period.
    Stub returning zeros — real impl joins relevant tables.
    """
    return {
        "new_matches": 0,
        "messages_exchanged": 0,
        "active_collabs": 0,
        "profile_views": 0,
    }


def _is_zero_activity(stats: dict[str, int]) -> bool:
    return all(v == 0 for v in stats.values())


async def _get_user_email(session: Any, user_id: str) -> str | None:
    """
    Fetch user email. In production this reads from a users table or calls auth-svc.
    Stub returns None to prevent sends in test/local.
    """
    return None
