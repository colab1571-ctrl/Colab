"""
analytics-svc — FastAPI application entry point.

Services:
- Event ingestion proxy (server-to-server; writes to Postgres mirror + forwards to PostHog)
- KPI rollup read API
- Celery Beat worker for nightly rollup jobs
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.config import get_settings
from app.routers.events import router as events_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # Register Celery beat schedule at startup
    import app.tasks.rollup  # noqa: F401
    yield


app = FastAPI(
    title="Colab Analytics Service",
    version="0.1.0",
    description=(
        "Event ingestion proxy → PostHog, KPI rollup computation (Celery Beat nightly)."
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

app.include_router(events_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "analytics-svc"}
