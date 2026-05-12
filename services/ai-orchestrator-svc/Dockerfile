FROM python:3.12-slim

WORKDIR /app

# System deps: ffmpeg for pydub audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copy DejaVu Bold font for PIL watermarking
RUN cp /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf /app/fonts/DejaVuSans-Bold.ttf

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "uvloop", "--workers", "1"]
