"""
analytics-svc — Celery application + Beat schedule.

Nightly rollup: 02:00 UTC every day.
"""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "analytics-svc",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.rollup"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    "nightly-kpi-rollup": {
        "task": "app.tasks.rollup.rollup_yesterday",
        "schedule": crontab(hour=2, minute=0),
    },
}
