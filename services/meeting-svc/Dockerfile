FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Copy workspace common package first (for layer caching)
COPY packages/colab-common /workspace/packages/colab-common
COPY services/meeting-svc/pyproject.toml /app/pyproject.toml

# Install deps
RUN uv pip install --system -e /workspace/packages/colab-common && \
    uv pip install --system -e /app

# Copy application code
COPY services/meeting-svc /app

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
