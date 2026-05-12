"""
matching-svc — Celery application + Beat schedule.

Beat tasks:
  matching.nightly_rerank          02:00 UTC daily
  matching.recommendation_set_gen  03:00 UTC daily
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "matching-svc",
    broker=_settings.rabbitmq_url,
    backend="rpc://",
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "nightly-rerank": {
            "task": "matching.nightly_rerank",
            "schedule": crontab(hour=2, minute=0),
        },
        "recommendation-set-generation": {
            "task": "matching.recommendation_set_gen",
            "schedule": crontab(hour=3, minute=0),
        },
        "cleanup-expired-hides": {
            "task": "discovery.cleanup_expired_hides",
            "schedule": crontab(hour=4, minute=0, day_of_week=0),  # weekly Sunday
        },
    },
)
