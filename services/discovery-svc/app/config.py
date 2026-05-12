"""discovery-svc configuration."""

from __future__ import annotations

import functools

from pydantic import field_validator
from pydantic_settings import BaseSettings


class DiscoverySettings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://colab:colab@localhost:5432/discovery_svc"

    # Redis
    redis_url: str = "redis://localhost:6379/3"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # Internal service endpoints
    profile_svc_url: str = "http://profile-svc:8000"
    billing_svc_url: str = "http://billing-svc:8000"
    matching_svc_url: str = "http://matching-svc:8000"

    # Service-to-service auth
    internal_service_secret: str = "dev-secret-change-me"

    # PostHog
    posthog_api_key: str = ""
    posthog_host: str = "https://app.posthog.com"

    # Feature flags
    feature_billing_entitlement_check: bool = False  # off until billing-svc (§013) lands

    # Daily cap
    rate_limit_feed_profiles_free_per_day: int = 30

    # Feed defaults
    feed_default_page_size: int = 20
    feed_max_page_size: int = 50

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
def get_settings() -> DiscoverySettings:
    return DiscoverySettings()
