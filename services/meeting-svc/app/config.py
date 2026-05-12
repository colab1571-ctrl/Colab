"""meeting-svc configuration."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class MeetingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEETING_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://colab:colab@localhost:5432/colab"
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # Internal service URLs
    chat_svc_url: str = "http://chat-svc:8000"
    collab_svc_url: str = "http://collab-svc:8000"

    # Service-to-service shared secret (HS256)
    service_shared_secret: str = "changeme"

    # Google Calendar / Meet
    # JSON key loaded from Secrets Manager at runtime — stored as a JSON string
    google_service_account_json: str = "{}"
    google_calendar_id: str = "primary"  # Colab shared calendar ID

    # Recall.ai
    recall_api_key: str = ""
    recall_webhook_secret: str = ""
    recall_api_base_url: str = "https://api.recall.ai/api/v1"
    recall_webhook_url: str = "https://api.colab.app/webhooks/recall"

    # S3 / CloudFront
    s3_bucket: str = "colab-meeting-artifacts-prod"
    s3_region: str = "us-east-1"
    cloudfront_domain: str = "cdn.colab.app"
    cloudfront_key_pair_id: str = ""
    cloudfront_private_key: str = ""  # PEM, newlines as \n

    # Signed URL TTL
    artifact_url_ttl_seconds: int = 3600  # 1 hour

    # Bot dispatch
    bot_name: str = "Colab Notes Bot"


@lru_cache
def get_settings() -> MeetingSettings:
    return MeetingSettings()
