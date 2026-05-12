"""Tests for colab_common.settings."""

import os

import pytest
from colab_common.settings import (
    DatabaseSettings,
    FeatureFlagSettings,
    JWTSettings,
    RedisSettings,
    Settings,
    get_settings,
)


def test_settings_defaults() -> None:
    """Settings has sensible defaults without any env vars set."""
    s = Settings()
    assert s.env == "local"
    assert s.brand_name == "Colab"
    assert s.aws_region == "us-east-1"


def test_settings_is_development() -> None:
    s = Settings(env="local")
    assert s.is_development is True


def test_settings_is_production() -> None:
    s = Settings(env="prod")
    assert s.is_production is True
    assert s.is_development is False


def test_database_settings_url_default() -> None:
    db = DatabaseSettings()
    assert "asyncpg" in db.url or "postgresql" in db.url


def test_redis_settings_defaults() -> None:
    r = RedisSettings()
    assert r.url.startswith("redis://")
    assert r.tls is False


def test_jwt_settings_defaults() -> None:
    j = JWTSettings()
    assert j.access_ttl_seconds == 900
    assert j.refresh_ttl_seconds == 2592000


def test_feature_flags_allowed_regions() -> None:
    f = FeatureFlagSettings()
    regions = f.allowed_regions
    assert "US" in regions
    assert "IN" in regions


def test_feature_flags_list_input() -> None:
    """Validator should accept both comma-string and list."""
    f = FeatureFlagSettings(region_allowlist="US,CA,AU")
    assert f.allowed_regions == ["US", "CA", "AU"]


def test_get_settings_is_cached() -> None:
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
