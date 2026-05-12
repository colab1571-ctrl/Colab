"""chat-svc configuration."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChatSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CHAT_",
        extra="ignore",
        env_file=".env.local",
    )

    # Moderation-svc internal URL (ClusterIP)
    moderation_svc_url: str = Field(default="http://moderation-svc:8000")
    moderation_scan_timeout_ms: int = Field(default=250)

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")

    # RabbitMQ
    rabbitmq_url: str = Field(default="amqp://colab:colab@localhost:5672/")

    # S3 / media
    s3_media_bucket: str = Field(default="colab-media")

    # Rate limits
    send_rate_per_minute: int = Field(default=30)
    typing_rate_seconds: int = Field(default=3)
    read_ack_rate_per_minute: int = Field(default=60)
    max_reconnect_frames: int = Field(default=5)

    # Message limits
    max_body_length: int = Field(default=4000)
    replay_page_size: int = Field(default=200)

    # Presence TTL seconds
    presence_ttl_seconds: int = Field(default=90)

    # Connection expiry (API GW hard limit = 7200s)
    connection_expiry_seconds: int = Field(default=7200)
    expiry_warning_at_seconds: int = Field(default=6900)  # 115 min


@lru_cache(maxsize=1)
def get_chat_settings() -> ChatSettings:
    return ChatSettings()
