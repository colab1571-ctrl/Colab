FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency installation
RUN pip install uv

# Copy workspace pyproject for colab-common
COPY packages/colab_common /workspace/colab_common
COPY services/notification-svc/pyproject.toml /app/pyproject.toml

# Install dependencies
RUN uv pip install --system --no-cache \
    /workspace/colab_common \
    fastapi \
    uvicorn[standard] \
    boto3 \
    Jinja2 \
    html2text \
    PyJWT[crypto] \
    celery[redis] \
    celery-redbeat \
    aio-pika \
    "redis[hiredis]" \
    "sqlalchemy[asyncio]" \
    alembic \
    asyncpg

# Copy application code
COPY services/notification-svc /app

# Copy templates
COPY services/notification-svc/templates /app/templates

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
