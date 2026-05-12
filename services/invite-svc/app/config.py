"""invite-svc configuration — extends colab_common.settings."""

from __future__ import annotations

import functools

from pydantic import field_validator
from pydantic_settings import BaseSettings


class InviteSettings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://colab:colab@localhost:5432/invite_svc"

    # Redis
    redis_url: str = "redis://localhost:6379/3"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # Internal service endpoints
    moderation_svc_url: str = "http://moderation-svc:8000"
    billing_svc_url: str = "http://billing-svc:8000"
    profile_svc_url: str = "http://profile-svc:8000"
    notification_svc_url: str = "http://notification-svc:8000"

    # Service-to-service auth
    internal_service_secret: str = "dev-secret-change-me"

    # Quota config
    free_invite_quota_per_week: int = 5
    invite_ttl_days: int = 30
    synopsis_max_chars: int = 250

    # Moderation
    synopsis_flag_threshold: float = 0.4
    moderation_timeout_seconds: float = 0.2  # 200ms; allow on timeout

    # Idempotency
    idempotency_ttl_seconds: int = 86400  # 24h
    send_dedup_window_seconds: int = 60

    # PostHog
    posthog_api_key: str = ""
    posthog_host: str = "https://app.posthog.com"

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
def get_settings() -> InviteSettings:
    return InviteSettings()
