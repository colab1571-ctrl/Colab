FROM python:3.12-slim AS base

# WeasyPrint system deps (Cairo + Pango + libffi)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir uv && uv pip install --system -e .

COPY . .

# API server
FROM base AS api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Celery worker (export tasks)
FROM base AS worker
CMD ["celery", "-A", "app.workers.celery_app", "worker", "--loglevel=info", "-Q", "collab_export,collab_archive"]

# Celery Beat (inactivity cadence)
FROM base AS beat
CMD ["celery", "-A", "app.workers.celery_app", "beat", "--loglevel=info"]
