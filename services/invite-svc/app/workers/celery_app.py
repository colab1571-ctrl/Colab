"""Celery application for invite-svc async workers."""

from __future__ import annotations

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "invite-svc",
    broker=settings.rabbitmq_url,
    backend="redis://" + settings.redis_url.split("//", 1)[-1],
    include=[
        "app.workers.ttl_tasks",
        "app.workers.beat_schedule",
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
        "app.workers.ttl_tasks.*": {"queue": "invite_ttl"},
    },
)
