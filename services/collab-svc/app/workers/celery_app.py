"""Celery application for collab-svc async workers."""

from __future__ import annotations

from celery import Celery

from app.config import get_collab_settings

settings = get_collab_settings()

celery_app = Celery(
    "collab-svc",
    broker=settings.rabbitmq_url,
    backend="redis://" + settings.redis_url.split("//", 1)[-1],
    include=[
        "app.workers.inactivity_tasks",
        "app.workers.export_tasks",
        "app.workers.archive_tasks",
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
        "app.workers.inactivity_tasks.*": {"queue": "collab_archive"},
        "app.workers.archive_tasks.*": {"queue": "collab_archive"},
        "app.workers.export_tasks.*": {"queue": "collab_export"},
    },
    # Hard timeout for export tasks (10 minutes)
    task_time_limit=600,
    task_soft_time_limit=540,
)
