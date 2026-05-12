"""geo-svc — Pydantic response schemas."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class AutocompleteFeature(BaseModel):
    id: str
    name: str
    place_name: str
    context: dict[str, Any] = Field(default_factory=dict)
    lng: Optional[float] = None
    lat: Optional[float] = None


class AutocompleteResponse(BaseModel):
    results: list[AutocompleteFeature]
    cached: bool = False


class ReverseGeocodeResponse(BaseModel):
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    cached: bool = False


class RadiusParamsResponse(BaseModel):
    lat: float
    lng: float
    radius_metres: float
    anywhere: bool
