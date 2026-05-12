"""
moderation-svc Celery application.

All moderation pipeline tasks share a single Celery app but may run on
dedicated queues (mod-fast, mod-image, mod-audio, mod-video, mod-beat).
"""

from __future__ import annotations

from colab_common.tasks import make_celery

celery_app = make_celery("moderation-svc")

# Register task modules so Celery autodiscovers them
celery_app.autodiscover_tasks(
    [
        "app.workers.scan_tasks",
        "app.workers.sla_tasks",
        "app.workers.dmca_tasks",
        "app.workers.propagation_tasks",
    ],
    force=True,
)
