"""
colab_common.settings — Layered configuration with AWS Secrets Manager support.

Load order (highest priority first):
1. AWS Secrets Manager (cached, TTL 60s)
2. AWS Parameter Store
3. Process environment / .env.local
"""

from __future__ import annotations

import functools
import json
import logging
import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Secrets Manager cache
# ---------------------------------------------------------------------------

_SM_CACHE: dict[str, tuple[Any, float]] = {}
_SM_TTL = 60  # seconds


def _sm_client() -> Any:
    region = os.environ.get("AWS_REGION", "us-east-1")
    return boto3.client("secretsmanager", region_name=region)


def get_secret(secret_id: str, *, ttl: int = _SM_TTL) -> dict[str, Any]:
    """Fetch and cache a JSON secret from Secrets Manager."""
    now = time.monotonic()
    cached = _SM_CACHE.get(secret_id)
    if cached and (now - cached[1]) < ttl:
        return dict(cached[0])
    try:
        client = _sm_client()
        resp = client.get_secret_value(SecretId=secret_id)
        value = json.loads(resp.get("SecretString", "{}"))
        _SM_CACHE[secret_id] = (value, now)
        return dict(value)
    except (ClientError, NoCredentialsError) as exc:
        logger.warning("Secrets Manager unavailable (%s); falling back to env.", exc)
        return {}


# ---------------------------------------------------------------------------
# Sub-settings classes
# ---------------------------------------------------------------------------


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_", extra="ignore")

    url: str = Field(default="postgresql+asyncpg://colab:colab@localhost:5432/colab")
    replica_url: str | None = Field(default=None)
    pool_min: int = Field(default=5)
    pool_max: int = Field(default=50)


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_", extra="ignore")

    url: str = Field(default="redis://localhost:6379/0")
    tls: bool = Field(default=False)


class JWTSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JWT_", extra="ignore")

    secret: str = Field(default="change-me-in-production")
    access_ttl_seconds: int = Field(default=900)
    refresh_ttl_seconds: int = Field(default=2592000)
    algorithm: str = Field(default="HS256")


class SentrySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SENTRY_", extra="ignore")

    dsn_api: str = Field(default="")
    traces_sample_rate: float = Field(default=0.1)
    profiles_sample_rate: float = Field(default=0.1)


class OTelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OTEL_", extra="ignore")

    exporter_otlp_endpoint: str = Field(default="http://localhost:4317")
    service_name: str = Field(default="colab-service")


class FeatureFlagSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FEATURE_", extra="ignore")

    ai_mockups_enabled: bool = Field(default=True)
    in_chat_ai_enabled: bool = Field(default=True)
    ads_enabled: bool = Field(default=False)
    marketing_notifications: bool = Field(default=False)
    region_allowlist: str = Field(default="US,CA,AU,NZ,IN")

    @field_validator("region_allowlist", mode="before")
    @classmethod
    def normalize_allowlist(cls, v: Any) -> str:
        if isinstance(v, list):
            return ",".join(v)
        return str(v)

    @property
    def allowed_regions(self) -> list[str]:
        return [r.strip() for r in self.region_allowlist.split(",") if r.strip()]


class RateLimitSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RATE_LIMIT_", extra="ignore")

    auth_per_ip_per_min: int = Field(default=10)
    invite_free_per_week: int = Field(default=5)
    feed_profiles_free_per_day: int = Field(default=30)


# ---------------------------------------------------------------------------
# Root Settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Root settings object. Import and instantiate once per service."""

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    env: str = Field(default="local")
    log_level: str = Field(default="INFO")
    brand_name: str = Field(default="Colab")
    app_domain: str = Field(default="app.colab.test")
    marketing_domain: str = Field(default="colab.test")
    admin_domain: str = Field(default="admin.colab.test")
    api_domain: str = Field(default="api.colab.test")

    # AWS
    aws_region: str = Field(default="us-east-1")
    aws_account_id: str = Field(default="")

    # RabbitMQ
    rabbitmq_url: str = Field(default="amqp://guest:guest@localhost:5672/")

    # Sub-settings (lazy-loaded)
    @functools.cached_property
    def db(self) -> DatabaseSettings:
        return DatabaseSettings()

    @functools.cached_property
    def redis(self) -> RedisSettings:
        return RedisSettings()

    @functools.cached_property
    def jwt(self) -> JWTSettings:
        return JWTSettings()

    @functools.cached_property
    def sentry(self) -> SentrySettings:
        return SentrySettings()

    @functools.cached_property
    def otel(self) -> OTelSettings:
        return OTelSettings()

    @functools.cached_property
    def features(self) -> FeatureFlagSettings:
        return FeatureFlagSettings()

    @functools.cached_property
    def rate_limits(self) -> RateLimitSettings:
        return RateLimitSettings()

    @property
    def is_production(self) -> bool:
        return self.env == "prod"

    @property
    def is_development(self) -> bool:
        return self.env in ("local", "dev")


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached)."""
    return Settings()
