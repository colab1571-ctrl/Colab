"""
geo-svc — PostGIS radius-query helper (internal API for discovery-svc).

Exposes a helper that builds the ST_DWithin SQL fragment used by
discovery-svc feed assembly. geo-svc itself is stateless (no DB);
this module provides the query builder + parameter normalizer so
discovery-svc can import it as an internal library call via HTTP.

The actual ST_DWithin execution lives in discovery-svc (which owns
the Postgres connection to the profile schema). This module:
  1. Validates and normalizes lat/lng/radius inputs.
  2. Returns the canonical query parameters dict.
  3. Exposes a FastAPI router at /internal/radius-params for HTTP callers.

Plan §9.1 canonical query:
  ST_DWithin(p.location_point::geography, ST_MakePoint($lng, $lat)::geography, $radius_metres)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from app.services.units import radius_to_metres, DEFAULT_RADIUS_KM, KM_TO_METRES


@dataclass
class RadiusParams:
    """Normalized parameters for a PostGIS radius query."""
    lat: float
    lng: float
    radius_metres: float
    anywhere: bool  # if True, spatial filter is skipped

    def to_dict(self) -> dict:
        return {
            "lat": self.lat,
            "lng": self.lng,
            "radius_metres": self.radius_metres,
            "anywhere": self.anywhere,
        }


def normalize_radius_params(
    lat: Optional[float],
    lng: Optional[float],
    radius_value: Optional[float],
    radius_unit: str = "km",
    anywhere: bool = False,
) -> RadiusParams:
    """
    Validate and normalize radius query parameters.

    - "Anywhere" mode: anywhere=True → returns RadiusParams with anywhere=True;
      spatial filter is skipped by the caller.
    - If lat/lng are None: treated as "anywhere".
    - radius_value=None: use locale default (80 km).
    - Validates lat in [-90, 90], lng in [-180, 180].
    """
    if anywhere or lat is None or lng is None:
        return RadiusParams(
            lat=0.0,
            lng=0.0,
            radius_metres=0.0,
            anywhere=True,
        )

    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"lat must be in [-90, 90]; got {lat}")
    if not (-180.0 <= lng <= 180.0):
        raise ValueError(f"lng must be in [-180, 180]; got {lng}")

    if radius_value is None or radius_value <= 0:
        radius_metres = DEFAULT_RADIUS_KM * KM_TO_METRES
    else:
        radius_metres = radius_to_metres(radius_value, radius_unit)

    return RadiusParams(
        lat=lat,
        lng=lng,
        radius_metres=radius_metres,
        anywhere=False,
    )


def build_st_dwithin_fragment(params: RadiusParams) -> tuple[str, dict]:
    """
    Return (sql_fragment, bind_params) for use in SQLAlchemy text queries.

    Usage:
        frag, params = build_st_dwithin_fragment(rp)
        query = f"SELECT ... FROM profile.profiles p WHERE {frag}"
    """
    if params.anywhere:
        return "true", {}

    sql = (
        "ST_DWithin("
        "p.location_point::geography, "
        "ST_MakePoint(:_geo_lng, :_geo_lat)::geography, "
        ":_geo_radius_metres"
        ")"
    )
    bind = {
        "_geo_lng": params.lng,
        "_geo_lat": params.lat,
        "_geo_radius_metres": params.radius_metres,
    }
    return sql, bind
