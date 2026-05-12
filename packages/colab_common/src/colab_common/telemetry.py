"""
colab_common.telemetry — One-call OTel + structlog + Sentry initialization.

IMPORTANT: Call telemetry.init(service_name) BEFORE importing FastAPI
to avoid double-instrumentation by the OTel FastAPI instrumentor.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# ContextVar for request_id propagation across async boundaries
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


def init(service_name: str, *, dsn: str | None = None, env: str = "local") -> None:
    """
    Initialize telemetry stack. Call ONCE at service startup BEFORE FastAPI import.

    - Configures structlog with JSON renderer + request_id injection
    - Initializes OpenTelemetry TracerProvider (OTLP over gRPC)
    - Initializes Sentry SDK

    Args:
        service_name: The name of the service (e.g., "gateway-svc")
        dsn: Sentry DSN. If None, reads from SENTRY_DSN_API env var.
        env: Deployment environment ("local", "dev", "staging", "prod")
    """
    _configure_structlog(service_name)
    _configure_otel(service_name, env)
    _configure_sentry(service_name, dsn=dsn, env=env)


def _configure_structlog(service_name: str) -> None:
    """Configure structlog with JSON output and request_id injection."""

    def add_service_name(
        _logger: Any, _method: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        event_dict["service"] = service_name
        return event_dict

    def add_request_id(
        _logger: Any, _method: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        rid = request_id_var.get("")
        if rid:
            event_dict["request_id"] = rid
        return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_service_name,
            add_request_id,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=logging.INFO)


def _configure_otel(service_name: str, env: str) -> None:
    """Configure OpenTelemetry with OTLP gRPC exporter."""
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                "service.name": service_name,
                "deployment.environment": env,
            }
        )
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter()  # Reads OTEL_EXPORTER_OTLP_ENDPOINT from env
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
    except ImportError:
        logging.warning("OpenTelemetry packages not installed — tracing disabled.")


def _configure_sentry(service_name: str, *, dsn: str | None, env: str) -> None:
    """Initialize Sentry SDK."""
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        is_prod = env == "prod"
        resolved_dsn = dsn or _env("SENTRY_DSN_API")
        if not resolved_dsn:
            return

        sentry_sdk.init(
            dsn=resolved_dsn,
            environment=env,
            release=_env("GIT_SHA", "unknown"),
            traces_sample_rate=0.1 if is_prod else 1.0,
            profiles_sample_rate=0.1 if is_prod else 1.0,
            integrations=[
                FastApiIntegration(),
                LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
            ],
            server_name=service_name,
        )
    except ImportError:
        logging.warning("sentry-sdk not installed — error tracking disabled.")


def _env(key: str, default: str = "") -> str:
    import os

    return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Injects X-Request-Id header; propagates to response; sets request_id_var ContextVar.
    If the incoming request already carries X-Request-Id (from upstream), we honour it.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        incoming = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = incoming
        token = request_id_var.set(incoming)
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-Id"] = incoming
            return response
        finally:
            request_id_var.reset(token)
