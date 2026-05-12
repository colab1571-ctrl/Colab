"""
support-svc configuration.

Settings sourced from environment variables, with safe defaults for local dev.
"""

from __future__ import annotations

import functools

from pydantic_settings import BaseSettings, SettingsConfigDict


class SupportSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SUPPORT_", case_sensitive=False)

    # OpenAI
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-large"
    openai_chat_model: str = "gpt-4o"

    # pgvector retrieval
    faq_top_k: int = 5
    faq_cosine_threshold: float = 0.72

    # Chatbot rate limit
    chatbot_rate_limit_per_hour: int = 10
    chatbot_max_history_turns: int = 6

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    status_page_cache_ttl: int = 60  # seconds

    # Statuspage.io
    statuspage_summary_url: str = (
        "https://status.atlassian.com/api/v2/summary.json"
    )  # stub; replace with real page URL

    # Billing svc (internal)
    billing_svc_url: str = "http://billing-svc:8000"
    billing_tier_cache_ttl: int = 300  # 5 min

    # Notification / RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # S3 (attachments)
    s3_attachments_bucket: str = "colab-support-attachments"


@functools.lru_cache(maxsize=1)
def get_support_settings() -> SupportSettings:
    return SupportSettings()
