"""Coordinate validation and geometry helpers.

Validation policy is described in ``docs/GIS_ARCHITECTURE.md`` section 3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.core.config import Settings, get_settings
from app.core.errors import InvalidCoordinatesError

#: Coordinates are stored to six decimal places (~0.11 m at the equator).
COORD_PRECISION = Decimal("0.000001")

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True, slots=True)
class Coordinates:
    latitude: Decimal
    longitude: Decimal

    @property
    def as_floats(self) -> tuple[float, float]:
        return float(self.latitude), float(self.longitude)


def quantize_coordinate(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(COORD_PRECISION, rounding=ROUND_HALF_UP)


def validate_coordinates(
    latitude: float | Decimal,
    longitude: float | Decimal,
    settings: Settings | None = None,
) -> Coordinates:
    """Validate and normalise a coordinate pair.

    Raises :class:`InvalidCoordinatesError` for an out-of-range value, a point
    outside the configured operating area, or the null-island signature of an
    unset GPS fix. Rejecting these loudly is deliberate: a silently accepted
    sign error sends responders to the wrong hemisphere.
    """
    settings = settings or get_settings()

    try:
        lat = quantize_coordinate(latitude)
        lon = quantize_coordinate(longitude)
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise InvalidCoordinatesError("Coordinates must be numeric.") from exc

    if not math.isfinite(float(lat)) or not math.isfinite(float(lon)):
        raise InvalidCoordinatesError("Coordinates must be finite numbers.")

    if not (Decimal("-90") <= lat <= Decimal("90")):
        raise InvalidCoordinatesError(
            "Latitude must be between -90 and 90.",
            details={"field": "latitude"},
        )
    if not (Decimal("-180") <= lon <= Decimal("180")):
        raise InvalidCoordinatesError(
            "Longitude must be between -180 and 180.",
            details={"field": "longitude"},
        )

    if lat == 0 and lon == 0:
        raise InvalidCoordinatesError(
            "Coordinates (0, 0) usually mean the device has no position fix. "
            "Please set the location manually."
        )

    in_bbox = (
        settings.geo_bbox_min_lat <= float(lat) <= settings.geo_bbox_max_lat
        and settings.geo_bbox_min_lon <= float(lon) <= settings.geo_bbox_max_lon
    )
    if not in_bbox:
        raise InvalidCoordinatesError(
            "The location is outside the area this deployment covers.",
            details={
                "operating_area": {
                    "min_lat": settings.geo_bbox_min_lat,
                    "max_lat": settings.geo_bbox_max_lat,
                    "min_lon": settings.geo_bbox_min_lon,
                    "max_lon": settings.geo_bbox_max_lon,
                }
            },
        )

    return Coordinates(latitude=lat, longitude=lon)


def to_ewkt(coords: Coordinates, srid: int = 4326) -> str:
    """Render coordinates as EWKT for a PostGIS ``geography`` column."""
    return f"SRID={srid};POINT({coords.longitude} {coords.latitude})"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres.

    Used only for display fallbacks and tests. Operational distance comes from
    PostGIS ``ST_Distance`` on ``geography``, which is geodesic rather than
    spherical.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def validate_bounding_box(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float
) -> None:
    """Reject an inverted or out-of-range viewport."""
    if min_lat >= max_lat or min_lon >= max_lon:
        raise InvalidCoordinatesError(
            "The bounding box minimum must be smaller than its maximum."
        )
    for value, name, limit in (
        (min_lat, "min_lat", 90),
        (max_lat, "max_lat", 90),
        (min_lon, "min_lon", 180),
        (max_lon, "max_lon", 180),
    ):
        if not -limit <= value <= limit:
            raise InvalidCoordinatesError(
                f"{name} is out of range.", details={"field": name}
            )
