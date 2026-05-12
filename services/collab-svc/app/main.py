"""
collab-svc — FastAPI application entry point.

Services:
- REST API: collaborations, status, feedback, export, activity history
- RabbitMQ consumers: match.created, chat.message.sent, block.created,
                       chat.media.scanned, profile.display_name_changed
- Celery workers: inactivity cadence (Beat), export generation
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from colab_common.telemetry import init as telemetry_init

telemetry_init("collab-svc")

from fastapi import FastAPI  # noqa: E402

from colab_common.errors import register_handlers  # noqa: E402
from colab_common.telemetry import RequestIDMiddleware  # noqa: E402

from app.routers.collabs import router as collabs_router  # noqa: E402
from app.routers.tasks import router as tasks_router  # noqa: E402
from app.routers.whiteboard import router as whiteboard_router  # noqa: E402

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # Start RabbitMQ consumers in background
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
    title="Colab Collab Service",
    version="0.1.0",
    description=(
        "Collaboration lifecycle: status machine, inactivity cadence, "
        "feedback collection, chat export (Premium), activity history. "
        "P9 extensions: Whiteboard (tldraw + Y.js CRDT) and Project Plan (tasks + comments)."
    ),
    lifespan=lifespan,
    docs_url="/docs" if os.environ.get("ENV", "local") in ("local", "dev") else None,
    redoc_url="/redoc" if os.environ.get("ENV", "local") in ("local", "dev") else None,
)

from colab_common.errors import register_handlers  # noqa: E402, F811
register_handlers(app)
app.add_middleware(RequestIDMiddleware)

app.include_router(collabs_router)
app.include_router(tasks_router)
app.include_router(whiteboard_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "collab-svc"}
