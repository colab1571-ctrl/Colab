"""Celery Beat schedule for collab-svc periodic jobs."""

from __future__ import annotations

from celery.schedules import crontab

from app.workers.celery_app import celery_app

celery_app.conf.beat_schedule = {
    # Hourly inactivity check: nudge (14d) + auto-archive (30d)
    "hourly-inactivity-check": {
        "task": "app.workers.inactivity_tasks.inactivity_check",
        "schedule": crontab(minute=0),  # Every hour at :00
        "options": {"queue": "collab_archive"},
    },
}
