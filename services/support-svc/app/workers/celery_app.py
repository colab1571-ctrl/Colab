"""
support-svc Celery application.

All support pipeline tasks share a single Celery app on queues:
  support-default   — general tasks (notifications, embedding)
  support-beat      — Beat scheduler tasks (SLA scan)
"""

from __future__ import annotations

from colab_common.tasks import make_celery

celery_app = make_celery("support-svc")

celery_app.autodiscover_tasks(
    [
        "app.workers.tasks",
        "app.workers.sla_tasks",
    ],
    force=True,
)
