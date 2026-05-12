"""
discovery-svc — FastAPI application entrypoint.

Implements Discovery FRs (Journey B):
  - Home feed: scroll + swipe modes (FR-B-1, FR-B-2)
  - Daily cap: Free 30/day, Premium unlimited (FR-B-3)
  - Filters: vocation, radius, experience, remote, last_active, collabs (FR-B-4)
  - Hide for 3 months (FR-B-5)
  - Save / like profile (FR-B-7)
  - AI Recommended Profiles "Picked for you" (FR-B-8)
  - Block-aware visibility (FR-B-9)
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from colab_common.errors import register_handlers
from colab_common.telemetry import RequestIDMiddleware
from colab_common.telemetry import init as telemetry_init

telemetry_init("discovery-svc")

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.routers.feed import router as feed_router  # noqa: E402
from app.routers.profiles import router as profiles_router  # noqa: E402
from app.routers.events import start_consumer  # noqa: E402

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    consumer_task = asyncio.create_task(
        start_consumer(settings.rabbitmq_url),
        name="discovery-svc-event-consumer",
    )
    logger.info("discovery-svc started; event consumer running")
    try:
        yield
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Colab Discovery Service",
    version="1.0.0",
    description=(
        "Home feed (scroll + swipe), filters, hide-3mo, saved profiles, "
        "AI Recommended 'Picked for you', daily cap enforcement."
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

register_handlers(app)
app.add_middleware(RequestIDMiddleware)

app.include_router(feed_router)
app.include_router(profiles_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "discovery-svc"}


@app.get("/version", include_in_schema=False)
async def version() -> dict[str, str]:
    import os
    return {
        "service": "discovery-svc",
        "version": "1.0.0",
        "git_sha": os.environ.get("GIT_SHA", "dev"),
    }
