"""
geo-svc tests.

Tests:
  - Mapbox autocomplete proxy round-trip (mock)
  - Mapbox reverse geocode proxy round-trip (mock)
  - Redis cache hit / miss behaviour
  - Radius query parameter normalization
  - Unit conversion (mi ↔ km ↔ metres)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
import httpx

from app.services.mapbox import MapboxClient, _normalize_autocomplete, _normalize_reverse, _autocomplete_cache_key, _reverse_cache_key
from app.services.radius import normalize_radius_params, build_st_dwithin_fragment
from app.services.units import (
    radius_to_metres,
    metres_to_radius,
    default_radius_metres,
    infer_unit_from_country,
    MI_TO_METRES,
    KM_TO_METRES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_mapbox_forward_response() -> dict:
    """Minimal Mapbox v6 forward geocoding response."""
    return {
        "features": [
            {
                "id": "place.123",
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-118.2437, 34.0522]},
                "properties": {
                    "name": "Los Angeles",
                    "full_address": "Los Angeles, California, United States",
                    "context": {
                        "place": {"name": "Los Angeles"},
                        "region": {"name": "California"},
                        "country": {"name": "United States"},
                    },
                },
            }
        ]
    }


@pytest.fixture
def fake_mapbox_reverse_response() -> dict:
    """Minimal Mapbox v6 reverse geocoding response."""
    return {
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-118.2437, 34.0522]},
                "properties": {
                    "name": "Los Angeles",
                    "context": {
                        "place": {"name": "Los Angeles"},
                        "region": {"name": "California"},
                        "country": {"name": "United States"},
                    },
                },
            }
        ]
    }


# ---------------------------------------------------------------------------
# Unit conversion tests
# ---------------------------------------------------------------------------

class TestUnitConversion:
    def test_miles_to_metres(self):
        assert abs(radius_to_metres(50.0, "mi") - 50.0 * MI_TO_METRES) < 0.01

    def test_km_to_metres(self):
        assert abs(radius_to_metres(80.0, "km") - 80_000.0) < 0.01

    def test_metres_to_miles_roundtrip(self):
        metres = radius_to_metres(50.0, "mi")
        back = metres_to_radius(metres, "mi")
        assert abs(back - 50.0) < 0.001

    def test_metres_to_km_roundtrip(self):
        metres = radius_to_metres(80.0, "km")
        back = metres_to_radius(metres, "km")
        assert abs(back - 80.0) < 0.001

    def test_invalid_unit_raises(self):
        with pytest.raises(ValueError, match="Unknown radius_unit"):
            radius_to_metres(50.0, "leagues")

    def test_default_radius_us(self):
        metres, unit = default_radius_metres("US")
        assert unit == "mi"
        assert abs(metres - 50.0 * MI_TO_METRES) < 1.0

    def test_default_radius_au(self):
        metres, unit = default_radius_metres("AU")
        assert unit == "km"
        assert abs(metres - 80_000.0) < 1.0

    def test_default_radius_unknown(self):
        metres, unit = default_radius_metres("XX")
        assert unit == "km"

    def test_infer_unit_us(self):
        assert infer_unit_from_country("US") == "mi"

    def test_infer_unit_ca(self):
        assert infer_unit_from_country("CA") == "mi"

    def test_infer_unit_gb(self):
        assert infer_unit_from_country("GB") == "km"

    def test_infer_unit_none(self):
        assert infer_unit_from_country(None) == "km"


# ---------------------------------------------------------------------------
# Radius params normalization tests
# ---------------------------------------------------------------------------

class TestRadiusParams:
    def test_anywhere_flag(self):
        params = normalize_radius_params(34.0, -118.0, 80, "km", anywhere=True)
        assert params.anywhere is True

    def test_none_lat_lng_is_anywhere(self):
        params = normalize_radius_params(None, None, 80, "km", anywhere=False)
        assert params.anywhere is True

    def test_valid_km_radius(self):
        params = normalize_radius_params(34.0, -118.0, 80, "km", anywhere=False)
        assert not params.anywhere
        assert abs(params.radius_metres - 80_000.0) < 1.0
        assert params.lat == 34.0
        assert params.lng == -118.0

    def test_valid_mi_radius(self):
        params = normalize_radius_params(34.0, -118.0, 50, "mi", anywhere=False)
        assert abs(params.radius_metres - 50.0 * MI_TO_METRES) < 1.0

    def test_invalid_lat_raises(self):
        with pytest.raises(ValueError, match="lat"):
            normalize_radius_params(95.0, -118.0, 80, "km")

    def test_invalid_lng_raises(self):
        with pytest.raises(ValueError, match="lng"):
            normalize_radius_params(34.0, 200.0, 80, "km")

    def test_none_radius_defaults_to_80km(self):
        params = normalize_radius_params(34.0, -118.0, None, "km")
        assert abs(params.radius_metres - 80_000.0) < 1.0

    def test_st_dwithin_fragment_non_anywhere(self):
        params = normalize_radius_params(34.0, -118.0, 80, "km")
        sql, bind = build_st_dwithin_fragment(params)
        assert "ST_DWithin" in sql
        assert "_geo_radius_metres" in bind
        assert "_geo_lat" in bind
        assert "_geo_lng" in bind

    def test_st_dwithin_fragment_anywhere(self):
        params = normalize_radius_params(None, None, None, "km", anywhere=True)
        sql, bind = build_st_dwithin_fragment(params)
        assert sql == "true"
        assert bind == {}


# ---------------------------------------------------------------------------
# Mapbox response normalizer tests
# ---------------------------------------------------------------------------

class TestMapboxNormalizers:
    def test_normalize_autocomplete(self, fake_mapbox_forward_response):
        features = _normalize_autocomplete(fake_mapbox_forward_response["features"])
        assert len(features) == 1
        assert features[0]["name"] == "Los Angeles"
        assert features[0]["lng"] == -118.2437
        assert features[0]["lat"] == 34.0522

    def test_normalize_reverse(self, fake_mapbox_reverse_response):
        result = _normalize_reverse(fake_mapbox_reverse_response["features"])
        assert result["city"] == "Los Angeles"
        assert result["region"] == "California"
        assert result["country"] == "United States"

    def test_normalize_autocomplete_empty(self):
        features = _normalize_autocomplete([])
        assert features == []

    def test_normalize_reverse_empty(self):
        result = _normalize_reverse([])
        assert result == {"city": None, "region": None, "country": None}


# ---------------------------------------------------------------------------
# Mapbox client proxy round-trip (mocked)
# ---------------------------------------------------------------------------

class TestMapboxClientAutocomplete:
    @pytest.mark.asyncio
    async def test_autocomplete_cache_miss_calls_mapbox(
        self, fake_mapbox_forward_response, monkeypatch
    ):
        """Cache miss → Mapbox API called → result cached → returned."""
        # Mock Redis to return None (cache miss)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(return_value=True)

        with patch("app.services.mapbox._get_redis", return_value=mock_redis):
            with respx.mock:
                respx.get("https://api.mapbox.com/search/geocode/v6/forward").mock(
                    return_value=httpx.Response(200, json=fake_mapbox_forward_response)
                )
                client = MapboxClient()
                client._token = "pk.test_token"
                results = await client.autocomplete("Los Angeles")

        assert len(results) == 1
        assert results[0]["name"] == "Los Angeles"
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_autocomplete_cache_hit_skips_mapbox(
        self, fake_mapbox_forward_response, monkeypatch
    ):
        """Cache hit → Mapbox API NOT called → cached result returned."""
        cached_data = _normalize_autocomplete(fake_mapbox_forward_response["features"])

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

        with patch("app.services.mapbox._get_redis", return_value=mock_redis):
            with respx.mock:
                # If Mapbox is called, the test fails (no matching route set up)
                client = MapboxClient()
                client._token = "pk.test_token"
                results = await client.autocomplete("Los Angeles")

        assert len(results) == 1
        assert results[0]["name"] == "Los Angeles"

    @pytest.mark.asyncio
    async def test_autocomplete_no_token_returns_empty(self):
        """No MAPBOX_SECRET_TOKEN → empty result, no API call."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("app.services.mapbox._get_redis", return_value=mock_redis):
            client = MapboxClient()
            client._token = ""
            results = await client.autocomplete("Los Angeles")

        assert results == []

    @pytest.mark.asyncio
    async def test_autocomplete_empty_query_returns_empty(self):
        """Empty query → immediately return []."""
        client = MapboxClient()
        results = await client.autocomplete("")
        assert results == []


class TestMapboxClientReverse:
    @pytest.mark.asyncio
    async def test_reverse_cache_miss_calls_mapbox(
        self, fake_mapbox_reverse_response, monkeypatch
    ):
        """Cache miss → Mapbox reverse API called → cached → returned."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(return_value=True)

        with patch("app.services.mapbox._get_redis", return_value=mock_redis):
            with respx.mock:
                respx.get("https://api.mapbox.com/search/geocode/v6/reverse").mock(
                    return_value=httpx.Response(200, json=fake_mapbox_reverse_response)
                )
                client = MapboxClient()
                client._token = "pk.test_token"
                result = await client.reverse_geocode(lat=34.0522, lng=-118.2437)

        assert result["city"] == "Los Angeles"
        assert result["region"] == "California"
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_reverse_cache_hit_skips_mapbox(
        self, fake_mapbox_reverse_response, monkeypatch
    ):
        """Cache hit → Mapbox NOT called → cached result returned."""
        cached = {"city": "Los Angeles", "region": "California", "country": "United States"}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached))

        with patch("app.services.mapbox._get_redis", return_value=mock_redis):
            client = MapboxClient()
            client._token = "pk.test_token"
            result = await client.reverse_geocode(lat=34.0522, lng=-118.2437)

        assert result["city"] == "Los Angeles"

    @pytest.mark.asyncio
    async def test_reverse_cache_key_uses_4_decimal_places(self):
        """Cache key truncates lat/lng to 4 decimal places for ~11m precision."""
        key1 = _reverse_cache_key(34.052199999, -118.243700001)
        key2 = _reverse_cache_key(34.0522, -118.2437)
        assert key1 == key2
