"""
geo-svc — Mapbox Geocoding API v6 client wrapper.

Never exposes MAPBOX_SECRET_TOKEN to the client. All requests are proxied
server-side. Results are cached in Redis:
  geo_autocomplete:<query_hash>   TTL 24 h
  geo_reverse:<lat4>:<lng4>       TTL 24 h

Prometheus counter: geo_svc_mapbox_calls_total (labels: endpoint, cached)

Plan §9.3:
  GET /geo/autocomplete?q=...&types=place,locality&limit=5
  GET /geo/reverse?lat=...&lng=...
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import httpx
import redis.asyncio as aioredis
from prometheus_client import Counter

from app.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()

# ---------------------------------------------------------------------------
# Prometheus metric
# ---------------------------------------------------------------------------

MAPBOX_CALLS = Counter(
    "geo_svc_mapbox_calls_total",
    "Total Mapbox API calls made by geo-svc",
    ["endpoint", "cached"],
)

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(_settings.redis_url, decode_responses=True)
    return _redis


def _autocomplete_cache_key(query: str, types: str, limit: int) -> str:
    payload = f"{query}|{types}|{limit}"
    h = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"geo_autocomplete:{h}"


def _reverse_cache_key(lat: float, lng: float) -> str:
    # Truncate to 4 decimal places (~11 m precision) for cache key
    lat4 = round(lat, 4)
    lng4 = round(lng, 4)
    return f"geo_reverse:{lat4}:{lng4}"


# ---------------------------------------------------------------------------
# Mapbox client
# ---------------------------------------------------------------------------

class MapboxClient:
    """
    Async Mapbox Geocoding v6 proxy.

    Uses MAPBOX_SECRET_TOKEN (never returned to clients).
    Caches all results in Redis with 24-hour TTL.
    """

    def __init__(self) -> None:
        self._token = _settings.mapbox_secret_token
        self._base = _settings.mapbox_geocoding_base_url
        self._timeout = 10.0

    async def autocomplete(
        self,
        q: str,
        types: str = "place,locality",
        limit: int | None = None,
        language: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Proxy Mapbox forward geocoding with autocomplete.

        Returns a list of feature dicts (id, name, place_name, geometry).
        Results are cached 24 h by (q, types, limit).
        """
        if not q or not q.strip():
            return []

        effective_limit = limit or _settings.mapbox_autocomplete_limit
        effective_lang = language or _settings.mapbox_default_language
        cache_key = _autocomplete_cache_key(q.strip(), types, effective_limit)
        r = _get_redis()

        cached = await r.get(cache_key)
        if cached:
            MAPBOX_CALLS.labels(endpoint="autocomplete", cached="true").inc()
            return json.loads(cached)

        MAPBOX_CALLS.labels(endpoint="autocomplete", cached="false").inc()

        if not self._token:
            logger.warning("MAPBOX_SECRET_TOKEN not set; returning empty autocomplete")
            return []

        params: dict[str, Any] = {
            "q": q.strip(),
            "types": types,
            "limit": effective_limit,
            "language": effective_lang,
            "access_token": self._token,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self._base}/forward", params=params)
            response.raise_for_status()
            data = response.json()

        features = _normalize_autocomplete(data.get("features", []))
        await r.set(cache_key, json.dumps(features), ex=_settings.geo_autocomplete_ttl)
        return features

    async def reverse_geocode(self, lat: float, lng: float) -> dict[str, Any]:
        """
        Proxy Mapbox reverse geocoding.

        Returns {"city": str, "region": str, "country": str}.
        Cached 24 h by (lat4, lng4).
        """
        cache_key = _reverse_cache_key(lat, lng)
        r = _get_redis()

        cached = await r.get(cache_key)
        if cached:
            MAPBOX_CALLS.labels(endpoint="reverse", cached="true").inc()
            return json.loads(cached)

        MAPBOX_CALLS.labels(endpoint="reverse", cached="false").inc()

        if not self._token:
            logger.warning("MAPBOX_SECRET_TOKEN not set; returning empty reverse geocode")
            return {"city": None, "region": None, "country": None}

        params: dict[str, Any] = {
            "longitude": lng,
            "latitude": lat,
            "types": "place,region,country",
            "language": _settings.mapbox_default_language,
            "access_token": self._token,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self._base}/reverse", params=params)
            response.raise_for_status()
            data = response.json()

        result = _normalize_reverse(data.get("features", []))
        await r.set(cache_key, json.dumps(result), ex=_settings.geo_reverse_ttl)
        return result


# ---------------------------------------------------------------------------
# Response normalizers
# ---------------------------------------------------------------------------

def _normalize_autocomplete(features: list[dict]) -> list[dict[str, Any]]:
    """Extract id, name, place_name, coordinates from Mapbox v6 features."""
    results = []
    for feat in features:
        props = feat.get("properties", {})
        coords = feat.get("geometry", {}).get("coordinates", [None, None])
        results.append({
            "id": feat.get("id", ""),
            "name": props.get("name", ""),
            "place_name": props.get("full_address") or props.get("place_formatted", ""),
            "context": {
                "place": props.get("context", {}).get("place", {}).get("name"),
                "region": props.get("context", {}).get("region", {}).get("name"),
                "country": props.get("context", {}).get("country", {}).get("name"),
            },
            "lng": coords[0],
            "lat": coords[1],
        })
    return results


def _normalize_reverse(features: list[dict]) -> dict[str, Any]:
    """Extract city, region, country from Mapbox v6 reverse features."""
    city = region = country = None
    for feat in features:
        props = feat.get("properties", {})
        ctx = props.get("context", {})
        if not city and ctx.get("place"):
            city = ctx["place"].get("name")
        if not region and ctx.get("region"):
            region = ctx["region"].get("name")
        if not country and ctx.get("country"):
            country = ctx["country"].get("name")
    return {"city": city, "region": region, "country": country}


# Module-level singleton
_mapbox_client: MapboxClient | None = None


def get_mapbox_client() -> MapboxClient:
    global _mapbox_client
    if _mapbox_client is None:
        _mapbox_client = MapboxClient()
    return _mapbox_client
