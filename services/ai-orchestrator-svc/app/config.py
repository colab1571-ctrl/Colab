"""ai-orchestrator-svc configuration."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_",
        extra="ignore",
        env_file=".env.local",
    )

    # OpenAI
    openai_api_key: str = Field(default="")
    openai_model_text: str = Field(default="gpt-4.1")
    openai_model_palette: str = Field(default="gpt-4.1-mini")
    openai_timeout_seconds: int = Field(default=30)
    openai_max_retries: int = Field(default=2)

    # Replicate
    replicate_api_token: str = Field(default="")
    replicate_webhook_secret: str = Field(default="")
    replicate_model_image_basic: str = Field(default="stability-ai/sdxl")
    replicate_model_image_pro: str = Field(default="black-forest-labs/flux-1.1-pro")
    replicate_model_audio_basic: str = Field(default="meta/musicgen")
    replicate_model_audio_pro: str = Field(default="stability-ai/stable-audio")
    replicate_webhook_url: str = Field(default="https://api.colab.app/webhooks/replicate")

    # AWS S3
    s3_bucket: str = Field(default="colab-ai-mockups")
    s3_cloudfront_domain: str = Field(default="cdn.colab.app")
    s3_signed_url_ttl_seconds: int = Field(default=300)  # 5 min
    aws_region: str = Field(default="us-east-1")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/2")

    # RabbitMQ
    rabbitmq_url: str = Field(default="amqp://colab:colab@localhost:5672/")

    # Internal service URLs
    billing_svc_url: str = Field(default="http://billing-svc:8000")
    chat_svc_url: str = Field(default="http://chat-svc:8000")
    moderation_svc_url: str = Field(default="http://moderation-svc:8000")
    notification_svc_url: str = Field(default="http://notification-svc:8000")
    collab_svc_url: str = Field(default="http://collab-svc:8000")
    profile_svc_url: str = Field(default="http://profile-svc:8000")

    # Rate limits
    command_rate_per_minute: int = Field(default=10)  # per user

    # Credit costs (admin-configurable; seed defaults)
    credit_mockup_image_basic: int = Field(default=20)
    credit_mockup_image_pro: int = Field(default=50)
    credit_mockup_audio_basic: int = Field(default=15)
    credit_mockup_audio_pro: int = Field(default=40)
    credit_summarize_chat: int = Field(default=5)
    credit_brainstorm: int = Field(default=5)
    credit_palette: int = Field(default=2)

    # Moderation threshold
    moderation_block_threshold: float = Field(default=0.7)
    moderation_pre_gen_threshold: float = Field(default=0.4)

    # Font path (bundled in Docker image)
    font_path: str = Field(default="/app/fonts/DejaVuSans-Bold.ttf")


@lru_cache(maxsize=1)
def get_ai_settings() -> AISettings:
    return AISettings()
