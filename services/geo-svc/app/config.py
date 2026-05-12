"""geo-svc configuration."""

from __future__ import annotations

import functools

from pydantic_settings import BaseSettings


class GeoSettings(BaseSettings):
    # Mapbox
    mapbox_secret_token: str = ""
    mapbox_geocoding_base_url: str = "https://api.mapbox.com/search/geocode/v6"

    # Redis cache
    redis_url: str = "redis://localhost:6379/5"

    # Cache TTLs (seconds)
    geo_autocomplete_ttl: int = 86_400   # 24 hours
    geo_reverse_ttl: int = 86_400        # 24 hours

    # Mapbox defaults
    mapbox_autocomplete_limit: int = 5
    mapbox_default_language: str = "en"

    # Environment
    env: str = "local"
    log_level: str = "INFO"

    @property
    def is_development(self) -> bool:
        return self.env in ("local", "dev", "development")

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


@functools.lru_cache
def get_settings() -> GeoSettings:
    return GeoSettings()
