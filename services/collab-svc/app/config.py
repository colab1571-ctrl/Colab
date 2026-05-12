"""collab-svc configuration."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class CollabSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COLLAB_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://colab:colab@localhost:5432/colab"
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # Internal service URLs
    billing_svc_url: str = "http://billing-svc:8000"
    chat_svc_url: str = "http://chat-svc:8000"
    invite_svc_url: str = "http://invite-svc:8000"

    # S3 / CloudFront
    s3_bucket: str = "colab-exports"
    s3_region: str = "us-east-1"
    cloudfront_domain: str = "cdn.example.com"
    cloudfront_key_pair_id: str = ""
    cloudfront_private_key: str = ""  # PEM, newlines as \n

    # Export TTL
    export_signed_url_ttl_days: int = 7

    # Service-to-service shared secret (HS256)
    service_shared_secret: str = "changeme"

    # Inactivity thresholds (days)
    nudge_days: int = 14
    archive_days: int = 30

    # Whiteboard settings
    whiteboard_idle_snapshot_seconds: int = 10
    whiteboard_redis_doc_ttl_seconds: int = 3600  # 1 hour hot-cache TTL
    whiteboard_op_retention_days: int = 30       # prune ops older than snapshot
    playwright_sidecar_url: str = "http://whiteboard-render:3000"  # Node.js render sidecar


@lru_cache
def get_collab_settings() -> CollabSettings:
    return CollabSettings()
