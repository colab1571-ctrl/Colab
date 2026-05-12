"""
Celery worker entrypoint for invite-svc.

Usage:
  celery -A app.workers._runner worker -Q invite_ttl --loglevel=info
  celery -A app.workers._runner beat --loglevel=info
"""

from app.workers.celery_app import celery_app  # noqa: F401
import app.workers.ttl_tasks  # noqa: F401 — ensure tasks are registered
import app.workers.beat_schedule  # noqa: F401 — ensure schedule is applied
