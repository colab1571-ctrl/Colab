# syntax=docker/dockerfile:1
# gateway-svc multi-stage build using uv

# ─── Stage 1: builder ────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /usr/local/bin/

WORKDIR /build

# Copy workspace config first (layer caching)
COPY pyproject.toml uv.lock* ./
COPY packages/colab_common/ ./packages/colab_common/
COPY services/gateway-svc/pyproject.toml ./services/gateway-svc/pyproject.toml

# Install dependencies into a virtual env
RUN uv sync --frozen --no-dev --package gateway-svc

# Copy application source
COPY services/gateway-svc/app/ ./services/gateway-svc/app/

# ─── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

# Copy only the virtual env from builder
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/services/gateway-svc/app /app/app
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

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
