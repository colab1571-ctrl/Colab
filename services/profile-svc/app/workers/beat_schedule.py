"""Celery Beat schedule for profile-svc nightly jobs."""

from __future__ import annotations

from celery.schedules import crontab

from app.workers.celery_app import celery_app

celery_app.conf.beat_schedule = {
    # Nightly health score recompute: 2AM UTC
    "nightly-health-score-recompute": {
        "task": "app.workers.health_score_tasks.recompute_all_health_scores",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "health_score"},
    },
    # Daily OAuth token refresh check (staggered by user_id % 60 buckets)
    "daily-oauth-refresh-check": {
        "task": "app.workers.health_score_tasks.refresh_expiring_oauth_tokens",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "health_score"},
    },
}
