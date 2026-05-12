"""
admin-svc — FastAPI application entry point.

Services:
- Moderator console (queue, case detail, action, DMCA workflow)
- Support console (ticket queue, detail, reply, escalate)
- Billing admin (tier definitions, entitlements, refunds, credit grants)
- User 360° composite endpoint
- Feature flag CRUD (with PostHog mirror)
- KPI rollup read proxy to analytics-svc
- Append-only AdminAuditLog
- Casbin RBAC (mod, support, billing_admin, super_admin)
- Defense-in-depth IP allowlist middleware
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.middleware import IPAllowlistMiddleware
from app.rbac import init_enforcer
from app.routers.audit import router as audit_router
from app.routers.billing import router as billing_router
from app.routers.flags import router as flags_router
from app.routers.kpi import router as kpi_router
from app.routers.moderation import router as moderation_router
from app.routers.support import router as support_router
from app.routers.users import router as users_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # Initialize Casbin enforcer with synchronous DB URL
    init_enforcer(settings.database_url_sync)
    yield


app = FastAPI(
    title="Colab Admin Service",
    version="0.1.0",
    description=(
        "Internal-only admin console API: moderation, support, billing, "
        "feature flags, KPI rollups, audit log."
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

# Defense-in-depth IP allowlist
app.add_middleware(IPAllowlistMiddleware)

# CORS: restrict to admin-web CloudFront origin only
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://admin.colab.app",
        "http://localhost:3002",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(moderation_router)
app.include_router(support_router)
app.include_router(billing_router)
app.include_router(users_router)
app.include_router(flags_router)
app.include_router(kpi_router)
app.include_router(audit_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "admin-svc"}


@app.get("/readyz", include_in_schema=False)
async def readyz() -> dict[str, str]:
    return {"status": "ok", "service": "admin-svc"}
