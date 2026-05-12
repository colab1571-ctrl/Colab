"""
geo-svc — FastAPI application entrypoint.

Stateless Mapbox geocoding proxy + PostGIS radius helper.
No database migrations (geo-svc has no tables).

Routes:
  GET /geo/autocomplete   — Mapbox forward geocoding (cached 24 h)
  GET /geo/reverse        — Mapbox reverse geocoding (cached 24 h)
  GET /internal/radius-params — PostGIS radius parameter normalizer
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from prometheus_client import make_asgi_app

try:
    from colab_common.errors import register_handlers
    from colab_common.telemetry import RequestIDMiddleware
    from colab_common.telemetry import init as telemetry_init
    telemetry_init("geo-svc")
    _have_common = True
except ImportError:
    _have_common = False

from app.config import get_settings
from app.routers.geo import router as geo_router

settings = get_settings()
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Colab Geo Service",
    version="1.0.0",
    description=(
        "Stateless Mapbox geocoding proxy (autocomplete + reverse) + "
        "PostGIS radius-query parameter helper. "
        "Never exposes MAPBOX_SECRET_TOKEN to clients."
    ),
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

if _have_common:
    register_handlers(app)
    app.add_middleware(RequestIDMiddleware)

app.include_router(geo_router)

# Prometheus metrics endpoint (internal scrape only)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "geo-svc"}


@app.get("/version", include_in_schema=False)
async def version() -> dict[str, str]:
    return {
        "service": "geo-svc",
        "version": "1.0.0",
        "git_sha": os.environ.get("GIT_SHA", "dev"),
    }
