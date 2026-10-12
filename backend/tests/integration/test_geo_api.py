"""Spatial queries against a live PostGIS instance."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.enums import UserRole

CHENNAI_LAT, CHENNAI_LON = 13.0827, 80.2707
# ~2.2 km north, ~11 km north: one degree of latitude is ~111 km.
NEAR_LAT = CHENNAI_LAT + 0.02
FAR_LAT = CHENNAI_LAT + 0.10


def seed(authed_client, make_user, incident_payload, **overrides) -> dict:
    client = authed_client(make_user(UserRole.CITIZEN))
    response = client.post("/api/v1/incidents", json=incident_payload | overrides)
    assert response.status_code == 201, response.text
    return response.json()


def test_nearby_finds_an_incident_inside_the_radius(
    authed_client, make_user, incident_payload
) -> None:
    seed(authed_client, make_user, incident_payload, latitude=NEAR_LAT)
    operator = authed_client(make_user(UserRole.DISPATCHER))

    body = operator.get(
        "/api/v1/geo/incidents/nearby",
        params={"latitude": CHENNAI_LAT, "longitude": CHENNAI_LON, "radius_km": 5},
    ).json()

    assert body["count"] == 1
    assert 2.0 < body["items"][0]["distance_km"] < 2.5


def test_nearby_excludes_an_incident_outside_the_radius(
    authed_client, make_user, incident_payload
) -> None:
    seed(authed_client, make_user, incident_payload, latitude=FAR_LAT)
    operator = authed_client(make_user(UserRole.DISPATCHER))

    body = operator.get(
        "/api/v1/geo/incidents/nearby",
        params={"latitude": CHENNAI_LAT, "longitude": CHENNAI_LON, "radius_km": 5},
    ).json()
    assert body["count"] == 0


def test_distance_is_geodesic_not_planar(
    authed_client, make_user, incident_payload
) -> None:
    """0.10 degrees of latitude is ~11.1 km; a planar approximation would drift."""
    seed(authed_client, make_user, incident_payload, latitude=FAR_LAT)
    operator = authed_client(make_user(UserRole.DISPATCHER))

    body = operator.get(
        "/api/v1/geo/incidents/nearby",
        params={"latitude": CHENNAI_LAT, "longitude": CHENNAI_LON, "radius_km": 20},
    ).json()
    assert 11.0 < body["items"][0]["distance_km"] < 11.2


def test_the_search_radius_is_capped(authed_client, make_user, incident_payload) -> None:
    from app.core.config import get_settings

    operator = authed_client(make_user(UserRole.DISPATCHER))
    body = operator.get(
        "/api/v1/geo/incidents/nearby",
        params={"latitude": CHENNAI_LAT, "longitude": CHENNAI_LON, "radius_km": 500},
    ).json()
    assert body["radius_km"] == get_settings().geo_max_search_radius_km


def test_nearby_rejects_a_point_outside_the_operating_area(
    authed_client, make_user
) -> None:
    operator = authed_client(make_user(UserRole.DISPATCHER))
    response = operator.get(
        "/api/v1/geo/incidents/nearby",
        params={"latitude": 51.5, "longitude": -0.12, "radius_km": 5},
    )
    assert response.status_code == 400


def test_nearby_rejects_a_non_positive_radius(authed_client, make_user) -> None:
    operator = authed_client(make_user(UserRole.DISPATCHER))
    response = operator.get(
        "/api/v1/geo/incidents/nearby",
        params={"latitude": CHENNAI_LAT, "longitude": CHENNAI_LON, "radius_km": 0},
    )
    assert response.status_code == 400


def test_nearby_orders_by_priority_then_distance(
    authed_client, make_user, incident_payload
) -> None:
    seed(
        authed_client,
        make_user,
        incident_payload,
        latitude=CHENNAI_LAT + 0.001,
        category="OTHER",
        people_trapped=False,
        medical_required=False,
        immediate_danger=False,
        people_affected=1,
    )
    seed(authed_client, make_user, incident_payload, latitude=NEAR_LAT)  # critical

    operator = authed_client(make_user(UserRole.DISPATCHER))
    items = operator.get(
        "/api/v1/geo/incidents/nearby",
        params={"latitude": CHENNAI_LAT, "longitude": CHENNAI_LON, "radius_km": 10},
    ).json()["items"]

    assert [item["priority_band"] for item in items] == ["CRITICAL", "LOW"]


def test_bbox_returns_geojson(authed_client, make_user, incident_payload) -> None:
    seed(authed_client, make_user, incident_payload)
    operator = authed_client(make_user(UserRole.DISPATCHER))

    body = operator.get(
        "/api/v1/geo/incidents/bbox",
        params={"min_lat": 12.5, "min_lon": 79.5, "max_lat": 13.5, "max_lon": 81.0},
    ).json()

    assert body["type"] == "FeatureCollection"
    assert body["count"] == 1
    feature = body["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Point"
    longitude, latitude = feature["geometry"]["coordinates"]
    # GeoJSON is [longitude, latitude] — reversing this is the classic GIS bug.
    assert round(longitude, 3) == round(CHENNAI_LON, 3)
    assert round(latitude, 3) == round(CHENNAI_LAT, 3)
    assert feature["properties"]["priority_band"] == "CRITICAL"


def test_bbox_excludes_incidents_outside_the_viewport(
    authed_client, make_user, incident_payload
) -> None:
    seed(authed_client, make_user, incident_payload)
    operator = authed_client(make_user(UserRole.DISPATCHER))

    body = operator.get(
        "/api/v1/geo/incidents/bbox",
        params={"min_lat": 9.0, "min_lon": 77.0, "max_lat": 10.0, "max_lon": 78.5},
    ).json()
    assert body["count"] == 0


def test_bbox_rejects_an_inverted_viewport(authed_client, make_user) -> None:
    operator = authed_client(make_user(UserRole.DISPATCHER))
    response = operator.get(
        "/api/v1/geo/incidents/bbox",
        params={"min_lat": 14.0, "min_lon": 81.0, "max_lat": 13.0, "max_lon": 80.0},
    )
    assert response.status_code == 400


def test_closed_incidents_are_hidden_from_the_live_map_by_default(
    client: TestClient, authed_client, make_user, incident_payload
) -> None:
    created = seed(authed_client, make_user, incident_payload)
    operator = authed_client(make_user(UserRole.DISPATCHER))

    for target in (
        "RECEIVED",
        "UNDER_REVIEW",
        "PRIORITIZED",
        "ASSIGNED",
        "RESOLVED",
        "CLOSED",
    ):
        operator.post(
            f"/api/v1/incidents/{created['id']}/status", json={"status": target}
        )

    live = operator.get(
        "/api/v1/geo/incidents/bbox",
        params={"min_lat": 12.5, "min_lon": 79.5, "max_lat": 13.5, "max_lon": 81.0},
    ).json()
    assert live["count"] == 0

    everything = operator.get(
        "/api/v1/geo/incidents/bbox",
        params={
            "min_lat": 12.5,
            "min_lon": 79.5,
            "max_lat": 13.5,
            "max_lon": 81.0,
            "open_only": False,
        },
    ).json()
    assert everything["count"] == 1


def test_the_spatial_index_is_used_for_radius_queries(db_session) -> None:
    """A radius query that falls back to a sequential scan will not survive
    production volume, so the plan is asserted, not assumed.

    The test table holds a handful of rows, and autovacuum re-analyses it during
    a long suite; on one page of data a sequential scan is genuinely the
    cheaper plan, so asserting the planner's *choice* made this test pass or
    fail by timing. Forbidding the sequential scan asks the real question: is
    the query written so that the GiST index can serve it?
    """
    from sqlalchemy import text

    db_session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = "\n".join(row[0] for row in db_session.execute(text("""
                EXPLAIN SELECT id FROM incidents
                WHERE ST_DWithin(
                    geom,
                    ST_SetSRID(ST_MakePoint(80.2707, 13.0827), 4326)::geography,
                    5000
                )
                """)))
    assert "ix_incidents_geom" in plan, plan
