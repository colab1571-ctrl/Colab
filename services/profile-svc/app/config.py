"""profile-svc configuration — extends colab_common.settings."""

from __future__ import annotations

import functools

from pydantic import field_validator
from pydantic_settings import BaseSettings


class ProfileSettings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://colab:colab@localhost:5432/profile_svc"

    # Redis
    redis_url: str = "redis://localhost:6379/2"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # S3 portfolio bucket
    s3_portfolio_bucket: str = "colab-portfolio-dev"
    s3_region: str = "us-east-1"
    presigned_url_ttl_seconds: int = 900  # 15 min

    # KMS
    kms_key_id_tokens: str = "alias/colab-oauth-tokens-dev"
    aws_region: str = "us-east-1"

    # Internal service endpoints
    moderation_svc_url: str = "http://moderation-svc:8000"
    geo_svc_url: str = "http://geo-svc:8000"
    notification_svc_url: str = "http://notification-svc:8000"

    # OAuth providers
    instagram_app_id: str = ""
    instagram_app_secret: str = ""
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    spotify_client_id: str = ""
    spotify_client_secret: str = ""

    # App domain for OAuth redirects
    app_domain: str = "https://app.colab.com"

    # PostHog
    posthog_api_key: str = ""
    posthog_host: str = "https://app.posthog.com"

    # Service-to-service auth
    internal_service_secret: str = "dev-secret-change-me"

    # Health score weights (admin-configurable, defaults per spec)
    health_completeness_weight: float = 0.40
    health_activity_weight: float = 0.30
    health_feedback_weight: float = 0.30

    # AI review weights
    ai_weight_openai: float = 0.35
    ai_weight_rekognition: float = 0.35
    ai_weight_dup: float = 0.20
    ai_weight_embedding_outlier: float = 0.10

    # Risk thresholds
    ai_risk_soft_warn: float = 0.40
    ai_risk_hide: float = 0.70
    ai_risk_severe: float = 0.90

    # Badge recheck rate limit
    badge_recheck_cooldown_hours: int = 24

    # Embedding
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 1536

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
def get_settings() -> ProfileSettings:
    return ProfileSettings()
