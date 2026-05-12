"""analytics-svc configuration."""

from __future__ import annotations

import os
from functools import lru_cache


class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://colab:colab@localhost:5432/colab",
    )
    database_url_sync: str = os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://colab:colab@localhost:5432/colab",
    )
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    posthog_ingest_url: str = os.environ.get(
        "POSTHOG_INGEST_URL", "https://app.posthog.com/capture/"
    )
    posthog_api_key: str = os.environ.get("POSTHOG_API_KEY", "")
    env: str = os.environ.get("ENV", "local")
    rollup_batch_size: int = int(os.environ.get("ROLLUP_BATCH_SIZE", "1000"))

    @property
    def is_development(self) -> bool:
        return self.env in ("local", "dev")


@lru_cache
def get_settings() -> Settings:
    return Settings()
