"""
moderation-svc Celery Beat schedule.

Applied at worker startup via celery_app.conf.beat_schedule.
Uses celery-redbeat for Redis-backed distributed beat (prevents duplicate
execution in multi-replica deployments).
"""

from __future__ import annotations

from celery.schedules import crontab

from app.workers.celery_app import celery_app

celery_app.conf.beat_schedule = {
    # SLA scanner — every 5 minutes
    "mod.sla.scan": {
        "task": "mod.sla.scan",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "mod-beat"},
    },
    # DMCA 24h hide enactment — every 5 minutes
    "mod.dmca.enact_hide": {
        "task": "mod.dmca.enact_hide",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "mod-beat"},
    },
    # Counter-notice statutory window scanner — every hour
    "mod.dmca.scan_counter_window": {
        "task": "mod.dmca.scan_counter_window",
        "schedule": crontab(minute="0"),
        "options": {"queue": "mod-beat"},
    },
}
