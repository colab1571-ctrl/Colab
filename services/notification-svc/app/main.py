"""
notification-svc — Multi-channel notification delivery service.

Channels: push (AWS SNS Mobile Push), email (AWS SES + MJML), in-app (RabbitMQ → chat-svc WS fanout).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from colab_common.telemetry import init as telemetry_init

telemetry_init("notification-svc")

from fastapi import FastAPI  # noqa: E402

from colab_common.errors import register_handlers  # noqa: E402
from colab_common.settings import get_settings  # noqa: E402
from colab_common.telemetry import RequestIDMiddleware  # noqa: E402

from .api.devices import router as devices_router  # noqa: E402
from .api.notifications import router as notifications_router  # noqa: E402
from .api.preferences import router as preferences_router  # noqa: E402

settings = get_settings()
logger = logging.getLogger(__name__)

_consumer_task: asyncio.Task | None = None  # type: ignore[type-arg]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    global _consumer_task
    # Start RabbitMQ consumer in background
    try:
        from .consumers.runner import start_consumer

        _consumer_task = asyncio.create_task(start_consumer())
        logger.info("RabbitMQ consumer started")
    except Exception as exc:
        logger.warning("Could not start RabbitMQ consumer: %s", exc)

    yield

    if _consumer_task:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Colab Notification Service",
    version="0.1.0",
    description="Multi-channel push/email/in-app notification delivery.",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
)

register_handlers(app)
app.add_middleware(RequestIDMiddleware)

# Routers
app.include_router(notifications_router)
app.include_router(preferences_router)
app.include_router(devices_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
