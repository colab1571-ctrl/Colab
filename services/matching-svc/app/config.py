"""matching-svc configuration."""

from __future__ import annotations

import functools

from pydantic import field_validator
from pydantic_settings import BaseSettings


class MatchingSettings(BaseSettings):
    # Database (read-write for matching schema; read-only role on profile schema)
    database_url: str = "postgresql+asyncpg://colab:colab@localhost:5432/matching_svc"

    # Redis
    redis_url: str = "redis://localhost:6379/4"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # Internal service
    profile_svc_url: str = "http://profile-svc:8000"
    internal_service_secret: str = "dev-secret-change-me"

    # OpenAI
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-large"
    openai_embedding_dimensions: int = 3072  # full fidelity per plan §2.4

    # Celery Beat schedule
    celery_beat_nightly_rerank_cron: str = "0 2 * * *"    # 02:00 UTC
    celery_beat_recs_cron: str = "0 3 * * *"              # 03:00 UTC

    # Ranking chunk size for nightly job
    rerank_chunk_size: int = 1000
    rerank_top_k: int = 200  # top-K candidates per user stored in match_scores

    # Environment
    env: str = "local"
    log_level: str = "INFO"

    @property
    def is_development(self) -> bool:
        return self.env in ("local", "dev", "development")

    @field_validator("database_url", mode="before")
    @classmethod
    def fix_db_url(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


@functools.lru_cache
def get_settings() -> MatchingSettings:
    return MatchingSettings()
