"""Celery application definition for ai-orchestrator-svc."""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/3")
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/4")

celery_app = Celery(
    "ai_orchestrator",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        "app.workers.expire_tasks",
        "app.workers.generation_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    "expire-mockup-assets": {
        "task": "app.workers.expire_tasks.expire_mockup_assets",
        "schedule": crontab(minute=0),  # hourly at :00
    },
    "expire-mockup-consents": {
        "task": "app.workers.expire_tasks.expire_pending_consents",
        "schedule": crontab(minute=30),  # hourly at :30
    },
}
