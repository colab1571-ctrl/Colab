"""
colab_common.tasks — Celery factory with redbeat scheduler + Sentry + OTel wiring.
"""

from __future__ import annotations

import logging
from typing import Any

from colab_common.settings import get_settings

logger = logging.getLogger(__name__)


def make_celery(service_name: str) -> Any:
    """
    Create a Celery app pre-wired with:
    - RabbitMQ broker from settings
    - Redis result backend
    - Redbeat scheduler (Redis-backed beat)
    - Sentry task instrumentation
    - OTel celery instrumentation
    - Structlog-based task logging
    - Base task class with retry defaults

    Usage in a service:
        celery_app = make_celery("auth-svc")

    Args:
        service_name: Used as the Celery app name.
    Returns:
        celery.Celery instance
    """
    try:
        import celery as celery_lib
        import celery.app.task as celery_task
    except ImportError as exc:
        raise ImportError("celery is required to use make_celery()") from exc

    settings = get_settings()

    # Derive Redis URL for result backend and redbeat
    redis_url = settings.redis.url

    app = celery_lib.Celery(service_name)

    app.conf.update(
        broker_url=settings.rabbitmq_url,
        result_backend=redis_url,
        # Reliability settings
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        # Serialization
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        # Timezone
        timezone="UTC",
        enable_utc=True,
        # Redbeat scheduler
        beat_scheduler="redbeat.RedBeatScheduler",
        redbeat_redis_url=redis_url,
        redbeat_lock_timeout=60,  # seconds; must exceed pod restart window
        # OTel
        worker_send_task_events=True,
        task_send_sent_event=True,
    )

    # -------------------------------------------------------------------------
    # Base task class with retry defaults
    # -------------------------------------------------------------------------

    class ColabBaseTask(celery_task.Task):  # type: ignore[misc]
        """
        Base Celery task with:
        - max_retries=5
        - Exponential backoff (2^attempt seconds, max 300s)
        - Structlog context binding
        - Sentry error capture on final failure
        """

        abstract = True
        max_retries = 5
        default_retry_delay = 5

        def on_failure(
            self,
            exc: Exception,
            task_id: str,
            args: Any,
            kwargs: Any,
            einfo: Any,
        ) -> None:
            logger.error(
                "Task failed permanently",
                extra={
                    "task": self.name,
                    "task_id": task_id,
                    "exc": str(exc),
                },
            )
            try:
                import sentry_sdk

                sentry_sdk.capture_exception(exc)
            except ImportError:
                pass
            super().on_failure(exc, task_id, args, kwargs, einfo)

        def on_retry(self, exc: Exception, task_id: str, args: Any, kwargs: Any, einfo: Any) -> None:
            logger.warning(
                "Task retry",
                extra={
                    "task": self.name,
                    "task_id": task_id,
                    "exc": str(exc),
                    "retries": self.request.retries,
                },
            )
            super().on_retry(exc, task_id, args, kwargs, einfo)

        def apply_async(self, *args: Any, countdown: float | None = None, **kwargs: Any) -> Any:
            if countdown is None and self.request.retries > 0:
                # Exponential backoff: 2^n seconds, capped at 300s
                countdown = min(2 ** self.request.retries, 300)
            return super().apply_async(*args, countdown=countdown, **kwargs)

    app.Task = ColabBaseTask

    # -------------------------------------------------------------------------
    # Sentry Celery integration
    # -------------------------------------------------------------------------
    try:
        from sentry_sdk.integrations.celery import CeleryIntegration

        import sentry_sdk

        if sentry_sdk.Hub.current.client:
            sentry_sdk.init(integrations=[CeleryIntegration()])
    except (ImportError, AttributeError):
        pass

    # -------------------------------------------------------------------------
    # OTel Celery instrumentation
    # -------------------------------------------------------------------------
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument()
    except ImportError:
        pass

    logger.info("Celery app created", extra={"service": service_name})
    return app
