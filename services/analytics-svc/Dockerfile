# syntax=docker/dockerfile:1
# analytics-svc Dockerfile — event ingestion proxy + KPI rollup worker

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /usr/local/bin/

WORKDIR /build

COPY pyproject.toml uv.lock* ./
COPY packages/colab_common/ ./packages/colab_common/
COPY services/analytics-svc/pyproject.toml ./services/analytics-svc/pyproject.toml

RUN uv sync --frozen --no-dev --package analytics-svc

COPY services/analytics-svc/app/ ./services/analytics-svc/app/
COPY services/analytics-svc/alembic/ ./services/analytics-svc/alembic/

FROM python:3.12-slim AS runtime

RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/services/analytics-svc/app /app/app
COPY --from=builder /build/services/analytics-svc/alembic /app/alembic
COPY --from=builder /build/packages/colab_common/src /app/colab_common_src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app:/app/colab_common_src" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8000

ARG GIT_SHA=dev
ARG IMAGE_TAG=dev
ENV GIT_SHA=${GIT_SHA} IMAGE_TAG=${IMAGE_TAG}

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"

# Default: FastAPI server. Override CMD for Celery Beat or Worker.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
