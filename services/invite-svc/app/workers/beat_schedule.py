"""Celery Beat schedule for invite-svc periodic jobs."""

from __future__ import annotations

from celery.schedules import crontab

from app.workers.celery_app import celery_app

celery_app.conf.beat_schedule = {
    # Hourly TTL archival: expire pending invites past 30-day archive_at
    "hourly-expire-stale-invites": {
        "task": "app.workers.ttl_tasks.expire_stale_invites",
        "schedule": crontab(minute=0),  # Every hour at :00
        "options": {"queue": "invite_ttl"},
    },
}
