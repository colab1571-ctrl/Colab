"""
Celery application for notification-svc.
Workers: dispatch tasks for each notification type.
Beat: weekly digest schedule.
"""

from __future__ import annotations

from colab_common.tasks import make_celery

celery_app = make_celery("notification-svc")

# Import task modules to register them
celery_app.autodiscover_tasks(
    [
        "app.workers.tasks",
        "app.workers.digest",
    ]
)
