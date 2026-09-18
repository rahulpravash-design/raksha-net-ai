"""Coordinate validation and distance helpers."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import InvalidCoordinatesError
from app.utils.geo import (
    haversine_km,
    quantize_coordinate,
    to_ewkt,
    validate_bounding_box,
    validate_coordinates,
)

CHENNAI = (13.0827, 80.2707)
MADURAI = (9.9252, 78.1198)


def test_valid_coordinates_are_normalised() -> None:
    coords = validate_coordinates(*CHENNAI)
    assert coords.latitude == Decimal("13.082700")
    assert coords.longitude == Decimal("80.270700")


def test_coordinates_are_quantised_to_six_places() -> None:
    assert quantize_coordinate(13.08271234567) == Decimal("13.082712")


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91.0, 80.0), (-91.0, 80.0), (13.0, 181.0), (13.0, -181.0)],
)
def test_out_of_range_coordinates_are_rejected(latitude: float, longitude: float) -> None:
    with pytest.raises(InvalidCoordinatesError):
        validate_coordinates(latitude, longitude)


def test_null_island_is_rejected() -> None:
    """(0, 0) is the signature of a device with no fix, not a location."""
    with pytest.raises(InvalidCoordinatesError) as excinfo:
        validate_coordinates(0.0, 0.0)
    assert "position fix" in str(excinfo.value)


def test_coordinates_outside_the_operating_area_are_rejected() -> None:
    """A mis-signed longitude must not quietly send responders elsewhere."""
    with pytest.raises(InvalidCoordinatesError) as excinfo:
        validate_coordinates(13.0827, -80.2707)
    assert excinfo.value.details["operating_area"]["min_lon"] == 68.0


def test_ewkt_puts_longitude_first() -> None:
    """PostGIS takes (x, y) — longitude then latitude. Reversing this is the
    classic GIS bug, so it is asserted explicitly."""
    ewkt = to_ewkt(validate_coordinates(*CHENNAI))
    assert ewkt == "SRID=4326;POINT(80.270700 13.082700)"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ((10.0, 78.0, 9.0, 80.0), "minimum"),
        ((9.0, 80.0, 10.0, 79.0), "minimum"),
    ],
)
def test_inverted_bounding_box_is_rejected(args: tuple[float, ...], message: str) -> None:
    with pytest.raises(InvalidCoordinatesError) as excinfo:
        validate_bounding_box(*args)
    assert message in str(excinfo.value)


def test_valid_bounding_box_passes() -> None:
    validate_bounding_box(9.0, 78.0, 14.0, 81.0)


def test_haversine_matches_a_known_distance() -> None:
    """Chennai to Madurai is about 422 km as the crow flies.

    Checked against the component distances: 3.1575 degrees of latitude is
    ~351 km, and 2.1509 degrees of longitude at ~11.5 degrees north is ~234 km.
    """
    distance = haversine_km(*CHENNAI, *MADURAI)
    assert distance == pytest.approx(422.1, abs=1.0)


def test_haversine_is_symmetric_and_zero_for_identity() -> None:
    assert haversine_km(*CHENNAI, *CHENNAI) == pytest.approx(0.0, abs=1e-9)
    assert haversine_km(*CHENNAI, *MADURAI) == pytest.approx(
        haversine_km(*MADURAI, *CHENNAI)
    )
