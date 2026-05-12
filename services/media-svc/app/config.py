"""media-svc configuration."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# MIME whitelist per kind
# ---------------------------------------------------------------------------

MIME_CAPS: dict[str, dict] = {
    "image": {
        "max_bytes": 10 * 1024 * 1024,
        "mimes": {
            "image/jpeg", "image/png", "image/gif", "image/webp", "image/heic",
        },
    },
    "audio": {
        "max_bytes": 50 * 1024 * 1024,
        "mimes": {
            "audio/mp4", "audio/mpeg", "audio/wav", "audio/ogg", "audio/aac",
        },
    },
    "video": {
        "max_bytes": 250 * 1024 * 1024,
        "mimes": {
            "video/mp4", "video/quicktime", "video/webm",
        },
    },
    "doc": {
        "max_bytes": 25 * 1024 * 1024,
        "mimes": {
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
        },
    },
    "voice": {
        "max_bytes": 10 * 1024 * 1024,
        "mimes": {
            "audio/mp4",
            "audio/mpeg",  # Android fallback per risk R-08
        },
    },
}


class MediaSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEDIA_",
        extra="ignore",
        env_file=".env.local",
    )

    s3_media_bucket: str = Field(default="colab-media")
    s3_presign_ttl_seconds: int = Field(default=300)  # 5 minutes

    # CloudFront signed URL config
    cloudfront_domain: str = Field(default="")
    cloudfront_key_pair_id: str = Field(default="")
    cloudfront_private_key_secret_arn: str = Field(default="")
    signed_url_ttl_seconds: int = Field(default=300)
    signed_url_cache_refresh_threshold_seconds: int = Field(default=60)

    # Moderation-svc
    moderation_svc_url: str = Field(default="http://moderation-svc:8000")
    moderation_scan_timeout_seconds: float = Field(default=15.0)

    # Chat-svc (for publishing the WS message after scan)
    redis_url: str = Field(default="redis://localhost:6379/0")
    rabbitmq_url: str = Field(default="amqp://colab:colab@localhost:5672/")

    # pHash dup-check
    phash_hamming_threshold: int = Field(default=6)

    # Per-message / per-collab daily caps (placeholder; enforced at confirm time)
    max_attachments_per_message: int = Field(default=1)


@lru_cache(maxsize=1)
def get_media_settings() -> MediaSettings:
    return MediaSettings()
