"""
media-svc — FastAPI application entry point.

Services:
- POST /media/upload-url  — presigned S3 PUT
- POST /media/confirm     — scan pipeline + WS delivery
- GET  /media/{s3_key}/signed-url  — rotating CloudFront signed URL
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from colab_common.telemetry import init as telemetry_init

telemetry_init("media-svc")

from fastapi import FastAPI  # noqa: E402

from colab_common.errors import register_handlers  # noqa: E402
from colab_common.settings import get_settings  # noqa: E402
from colab_common.telemetry import RequestIDMiddleware  # noqa: E402

from app.routers.media import router as media_router  # noqa: E402

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    yield


app = FastAPI(
    title="Colab Media Service",
    version="0.1.0",
    description=(
        "Presigned S3 upload, moderation scan pipeline, "
        "CloudFront signed URL serving."
    ),
    lifespan=lifespan,
    docs_url="/docs" if os.environ.get("ENV", "local") in ("local", "dev") else None,
    redoc_url="/redoc" if os.environ.get("ENV", "local") in ("local", "dev") else None,
)

register_handlers(app)
app.add_middleware(RequestIDMiddleware)

app.include_router(media_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "media-svc"}
