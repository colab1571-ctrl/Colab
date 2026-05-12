"""admin-svc configuration."""

from __future__ import annotations

import os
from functools import lru_cache


class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://colab:colab@localhost:5432/colab",
    )
    database_url_sync: str = os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://colab:colab@localhost:5432/colab",
    )
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    jwt_secret: str = os.environ.get("JWT_SECRET", "dev-secret")
    admin_jwt_secret: str = os.environ.get("ADMIN_JWT_SECRET", "admin-dev-secret")
    admin_jwt_expiry_seconds: int = int(os.environ.get("ADMIN_JWT_EXPIRY_SECONDS", "3600"))
    admin_refresh_expiry_seconds: int = int(
        os.environ.get("ADMIN_REFRESH_EXPIRY_SECONDS", "86400")
    )
    env: str = os.environ.get("ENV", "local")
    # Comma-separated IPs for defense-in-depth middleware
    admin_ip_allowlist: list[str] = [
        ip.strip()
        for ip in os.environ.get("ADMIN_IP_ALLOWLIST", "127.0.0.1,::1").split(",")
        if ip.strip()
    ]
    # External service URLs (admin-svc fans out to these)
    auth_svc_url: str = os.environ.get("AUTH_SVC_URL", "http://auth-svc:8000")
    profile_svc_url: str = os.environ.get("PROFILE_SVC_URL", "http://profile-svc:8000")
    billing_svc_url: str = os.environ.get("BILLING_SVC_URL", "http://billing-svc:8000")
    moderation_svc_url: str = os.environ.get(
        "MODERATION_SVC_URL", "http://moderation-svc:8000"
    )
    support_svc_url: str = os.environ.get("SUPPORT_SVC_URL", "http://support-svc:8000")
    analytics_svc_url: str = os.environ.get(
        "ANALYTICS_SVC_URL", "http://analytics-svc:8000"
    )
    identity_svc_url: str = os.environ.get(
        "IDENTITY_SVC_URL", "http://identity-svc:8000"
    )
    posthog_api_key: str = os.environ.get("POSTHOG_PERSONAL_API_KEY", "")
    posthog_project_id: str = os.environ.get("POSTHOG_PROJECT_ID", "")
    # Support credit-grant daily cap for support role
    support_credit_grant_daily_cap_cents: int = int(
        os.environ.get("SUPPORT_CREDIT_GRANT_DAILY_CAP_CENTS", "20000")
    )
    support_credit_grant_single_cap_cents: int = int(
        os.environ.get("SUPPORT_CREDIT_GRANT_SINGLE_CAP_CENTS", "2000")
    )

    @property
    def is_production(self) -> bool:
        return self.env == "prod"

    @property
    def is_development(self) -> bool:
        return self.env in ("local", "dev")


@lru_cache
def get_settings() -> Settings:
    return Settings()
