"""
colab_common — Shared Python library for all Colab FastAPI services.

Usage in a service:
    from colab_common.settings import Settings
    from colab_common.db import get_session
    from colab_common.auth import require_user
    from colab_common.telemetry import init as telemetry_init
    from colab_common.errors import register_handlers
"""

__version__ = "0.1.0"
__all__ = [
    "settings",
    "db",
    "auth",
    "errors",
    "events",
    "rate_limit",
    "idempotency",
    "telemetry",
    "tasks",
    "testing",
]
