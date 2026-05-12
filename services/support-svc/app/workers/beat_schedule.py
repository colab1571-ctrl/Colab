"""
support-svc Celery Beat schedule.

Uses celery-redbeat for Redis-backed distributed beat (prevents duplicate
execution in multi-replica deployments).
"""

from __future__ import annotations

from celery.schedules import crontab

from app.workers.celery_app import celery_app

celery_app.conf.beat_schedule = {
    # SLA scanner — every 5 minutes (spec §3.1)
    "support.sla.scan": {
        "task": "support.sla.scan",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "support-beat"},
    },
    # Nightly chatbot session cleanup
    "support.purge_expired_chatbot_sessions": {
        "task": "support.purge_expired_chatbot_sessions",
        "schedule": crontab(hour="3", minute="0"),
        "options": {"queue": "support-default"},
    },
}
