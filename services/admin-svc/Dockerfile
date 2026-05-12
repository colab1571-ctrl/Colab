# syntax=docker/dockerfile:1
# admin-svc Dockerfile — internal-only admin console backend

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /usr/local/bin/

WORKDIR /build

COPY pyproject.toml uv.lock* ./
COPY packages/colab_common/ ./packages/colab_common/
COPY services/admin-svc/pyproject.toml ./services/admin-svc/pyproject.toml

RUN uv sync --frozen --no-dev --package admin-svc

COPY services/admin-svc/app/ ./services/admin-svc/app/
COPY services/admin-svc/alembic/ ./services/admin-svc/alembic/
COPY services/admin-svc/infra/ ./services/admin-svc/infra/

FROM python:3.12-slim AS runtime

RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/services/admin-svc/app /app/app
COPY --from=builder /build/services/admin-svc/alembic /app/alembic
COPY --from=builder /build/services/admin-svc/infra /app/infra
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

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
