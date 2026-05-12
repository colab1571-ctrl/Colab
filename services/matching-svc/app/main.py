"""
matching-svc — FastAPI application entrypoint.

Implements:
  - Embedding ranking engine (HNSW 3072-d pgvector)
  - Nightly Celery Beat rerank + recommendation set generation
  - On-demand re-rank on profile events
  - 9×9 affinity matrix (admin-editable)
  - Internal match score + candidates API
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from colab_common.errors import register_handlers
from colab_common.telemetry import RequestIDMiddleware
from colab_common.telemetry import init as telemetry_init

telemetry_init("matching-svc")

from fastapi import FastAPI  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.routers.match import router as match_router  # noqa: E402
from app.routers.events import start_consumer  # noqa: E402
from app.services.affinity_cache import warm_affinity_cache  # noqa: E402

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # Warm affinity matrix cache on startup
    await warm_affinity_cache()

    consumer_task = asyncio.create_task(
        start_consumer(settings.rabbitmq_url),
        name="matching-svc-event-consumer",
    )
    logger.info("matching-svc started; affinity cache warmed; event consumer running")
    try:
        yield
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Colab Matching Service",
    version="1.0.0",
    description=(
        "Embedding-based ranking, 9×9 affinity matrix, nightly rerank Celery Beat, "
        "on-demand re-rank, match score API."
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

register_handlers(app)
app.add_middleware(RequestIDMiddleware)

app.include_router(match_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "matching-svc"}


@app.get("/version", include_in_schema=False)
async def version() -> dict[str, str]:
    import os
    return {
        "service": "matching-svc",
        "version": "1.0.0",
        "git_sha": os.environ.get("GIT_SHA", "dev"),
    }
