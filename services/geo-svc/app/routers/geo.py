"""
geo-svc — geo router.

Endpoints:
  GET /geo/autocomplete?q=...&types=...&limit=...
  GET /geo/reverse?lat=...&lng=...
  GET /internal/radius-params (for discovery-svc)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.geo import AutocompleteResponse, AutocompleteFeature, ReverseGeocodeResponse, RadiusParamsResponse
from app.services.mapbox import get_mapbox_client
from app.services.radius import normalize_radius_params
from app.services.units import radius_to_metres

router = APIRouter(tags=["geo"])
logger = logging.getLogger(__name__)


@router.get("/geo/autocomplete", response_model=AutocompleteResponse)
async def autocomplete(
    q: str = Query(..., min_length=1, description="Search query for city/locality autocomplete"),
    types: str = Query("place,locality", description="Comma-separated Mapbox feature types"),
    limit: int = Query(5, ge=1, le=10, description="Max results to return"),
) -> AutocompleteResponse:
    """
    Proxy Mapbox forward geocoding with autocomplete.
    MAPBOX_SECRET_TOKEN never exposed to client.
    Results cached 24 h in Redis.
    """
    try:
        client = get_mapbox_client()
        features = await client.autocomplete(q=q, types=types, limit=limit)
        return AutocompleteResponse(
            results=[AutocompleteFeature(**f) for f in features],
        )
    except Exception as exc:
        logger.error("autocomplete error: %s", exc)
        raise HTTPException(status_code=502, detail="geocoding service unavailable") from exc


@router.get("/geo/reverse", response_model=ReverseGeocodeResponse)
async def reverse_geocode(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude"),
    lng: float = Query(..., ge=-180.0, le=180.0, description="Longitude"),
) -> ReverseGeocodeResponse:
    """
    Proxy Mapbox reverse geocoding — returns city + region.
    Results cached 24 h by (lat4, lng4).
    """
    try:
        client = get_mapbox_client()
        result = await client.reverse_geocode(lat=lat, lng=lng)
        return ReverseGeocodeResponse(**result)
    except Exception as exc:
        logger.error("reverse geocode error: %s", exc)
        raise HTTPException(status_code=502, detail="geocoding service unavailable") from exc


@router.get("/internal/radius-params", response_model=RadiusParamsResponse)
async def get_radius_params(
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    radius_value: Optional[float] = Query(None),
    radius_unit: str = Query("km", pattern="^(mi|km)$"),
    anywhere: bool = Query(False),
) -> RadiusParamsResponse:
    """
    Internal endpoint for discovery-svc to normalize radius parameters.
    Returns PostGIS-ready parameters including radius in metres.
    """
    try:
        params = normalize_radius_params(
            lat=lat,
            lng=lng,
            radius_value=radius_value,
            radius_unit=radius_unit,
            anywhere=anywhere,
        )
        return RadiusParamsResponse(**params.to_dict())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
