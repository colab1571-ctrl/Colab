FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy workspace common + service
COPY libs/colab_common /workspace/libs/colab_common
COPY services/invite-svc /workspace/services/invite-svc

WORKDIR /workspace/services/invite-svc

RUN uv sync --no-dev

ENV PYTHONPATH=/workspace
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
