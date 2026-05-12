"""Celery application for meeting-svc async workers."""

from __future__ import annotations

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "meeting-svc",
    broker=settings.rabbitmq_url,
    backend="redis://" + settings.redis_url.split("//", 1)[-1],
    include=[
        "app.workers.bot_tasks",
        "app.workers.webhook_tasks",
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
    task_routes={
        "app.workers.bot_tasks.*": {"queue": "meeting_bot"},
        "app.workers.webhook_tasks.*": {"queue": "meeting_webhook"},
    },
    # Bot dispatch: 10-minute timeout (Recall.ai create_bot is fast)
    task_time_limit=600,
    task_soft_time_limit=540,
)
