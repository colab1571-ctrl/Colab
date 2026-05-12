"""
meeting-svc — FastAPI application entry point.

Services:
- REST API: meeting scheduling, bot consent, artifact access
- Recall.ai webhook handler (HMAC-verified)
- Celery workers: bot dispatch, webhook processing
- RabbitMQ consumers: meeting.transcript_ready → chat system message
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from colab_common.telemetry import init as telemetry_init

telemetry_init("meeting-svc")

from fastapi import FastAPI  # noqa: E402

from colab_common.errors import register_handlers  # noqa: E402
from colab_common.telemetry import RequestIDMiddleware  # noqa: E402

from app.routers.meetings import router as meetings_router  # noqa: E402

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    consumer_task = None
    try:
        from app.workers.event_consumers import start_consumers
        consumer_task = asyncio.ensure_future(start_consumers())
    except Exception as exc:
        logger.warning("RabbitMQ consumer startup failed: %s", exc)

    yield

    if consumer_task:
        consumer_task.cancel()


app = FastAPI(
    title="Colab Meeting Service",
    version="0.1.0",
    description=(
        "Google Meet scheduling via Calendar API, Recall.ai bot management, "
        "transcript ingestion, webhook processing."
    ),
    lifespan=lifespan,
    docs_url="/docs" if os.environ.get("ENV", "local") in ("local", "dev") else None,
    redoc_url="/redoc" if os.environ.get("ENV", "local") in ("local", "dev") else None,
)

register_handlers(app)
app.add_middleware(RequestIDMiddleware)

app.include_router(meetings_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "meeting-svc"}
