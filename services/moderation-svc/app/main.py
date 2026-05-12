"""
moderation-svc — FastAPI application entry point.

Services:
- Risk-tiered moderation pipeline (Celery workers)
- Moderator case management API
- Report intake API
- DMCA + counter-notice workflow API
- Internal scan APIs (for §007/§004/§006)
- Action propagation via RabbitMQ
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from colab_common.telemetry import init as telemetry_init

telemetry_init("moderation-svc")

from fastapi import FastAPI  # noqa: E402
from colab_common.errors import register_handlers  # noqa: E402
from colab_common.settings import get_settings  # noqa: E402
from colab_common.telemetry import RequestIDMiddleware  # noqa: E402

from app.routers.cases import router as cases_router  # noqa: E402
from app.routers.dmca import router as dmca_router  # noqa: E402
from app.routers.internal import router as internal_router  # noqa: E402
from app.routers.reports import router as reports_router  # noqa: E402

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # Import beat schedule so it is registered on startup
    import app.workers.beat_schedule  # noqa: F401
    yield


app = FastAPI(
    title="Colab Moderation Service",
    version="0.1.0",
    description=(
        "Risk-tiered content moderation pipeline, DMCA workflow, "
        "moderator queue and action APIs."
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

register_handlers(app)
app.add_middleware(RequestIDMiddleware)

# Routers
app.include_router(reports_router)
app.include_router(dmca_router)
app.include_router(cases_router)
app.include_router(internal_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "moderation-svc"}
