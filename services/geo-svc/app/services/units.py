"""
geo-svc — locale-aware unit conversion helpers.

Plan §9.2:
  US, Canada  → default 50 mi  (80 467 m)
  AU, NZ, IN  → default 80 km  (80 000 m)

Profile.radius_unit stores "mi" or "km".
"Anywhere" = open_to_remote=True + radius=None → spatial filter skipped.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MI_TO_METRES: float = 1609.344
KM_TO_METRES: float = 1000.0

# Locale → default radius unit
LOCALE_UNIT_MAP: dict[str, str] = {
    "US": "mi",
    "CA": "mi",  # Canada
    "AU": "km",
    "NZ": "km",
    "IN": "km",  # India
}

# Default radius values by unit
DEFAULT_RADIUS_MI: float = 50.0
DEFAULT_RADIUS_KM: float = 80.0


# ---------------------------------------------------------------------------
# Conversion functions
# ---------------------------------------------------------------------------

def radius_to_metres(radius_value: float, radius_unit: str) -> float:
    """
    Convert a radius value to metres for PostGIS ST_DWithin.

    Args:
        radius_value: Numeric radius (e.g. 50 for 50 miles).
        radius_unit: "mi" or "km".

    Returns:
        Equivalent value in metres (float).
    """
    unit = radius_unit.strip().lower()
    if unit == "mi":
        return radius_value * MI_TO_METRES
    elif unit == "km":
        return radius_value * KM_TO_METRES
    else:
        raise ValueError(f"Unknown radius_unit: {radius_unit!r}; expected 'mi' or 'km'")


def metres_to_radius(metres: float, radius_unit: str) -> float:
    """Convert metres back to the given unit (for display purposes)."""
    unit = radius_unit.strip().lower()
    if unit == "mi":
        return metres / MI_TO_METRES
    elif unit == "km":
        return metres / KM_TO_METRES
    else:
        raise ValueError(f"Unknown radius_unit: {radius_unit!r}")


def default_radius_metres(country_code: str | None = None) -> tuple[float, str]:
    """
    Return (default_radius_metres, unit) for a given 2-letter country code.

    Falls back to km/80km for unknown locales.
    """
    if country_code:
        unit = LOCALE_UNIT_MAP.get(country_code.upper(), "km")
    else:
        unit = "km"

    if unit == "mi":
        return DEFAULT_RADIUS_MI * MI_TO_METRES, "mi"
    else:
        return DEFAULT_RADIUS_KM * KM_TO_METRES, "km"


def infer_unit_from_country(country_code: str | None) -> str:
    """
    Return "mi" for US/CA, "km" for everything else.
    """
    if country_code and country_code.upper() in ("US", "CA"):
        return "mi"
    return "km"
