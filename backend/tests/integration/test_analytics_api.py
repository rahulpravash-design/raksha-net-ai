"""Analytics (Phase 14).

Two properties under test above the ordinary happy-path/role checks: the
time-based metrics compute the gap they claim to, and the hotspot endpoint
never leaks a raw incident coordinate — only a coarsened grid cell
(``CLAUDE.md`` section 5).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.dispatch import Dispatch
from app.models.enums import UserRole
from app.models.incident import Incident

CHENNAI = (13.0827, 80.2707)


def report(client: TestClient, payload: dict, **overrides: object) -> dict:
    response = client.post("/api/v1/incidents", json=payload | overrides)
    assert response.status_code == 201, response.text
    return response.json()


def make_resource(client: TestClient, **overrides: object) -> dict:
    payload = {
        "call_sign": f"AMB-{uuid.uuid4().hex[:6]}",
        "name": "Test Ambulance",
        "resource_type": "AMBULANCE",
        "latitude": CHENNAI[0],
        "longitude": CHENNAI[1],
    }
    payload.update(overrides)
    response = client.post("/api/v1/resources", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def authenticate_as(client: TestClient, user) -> TestClient:
    token, _ = create_access_token(user.id, user.role.value)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def test_analytics_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/analytics/category-breakdown").status_code == 401


def test_a_responder_cannot_view_analytics(
    client: TestClient, make_user, incident_payload
) -> None:
    """Phase 14 is restricted to dispatch-capable roles, not every operational one."""
    responder = make_user(UserRole.RESPONDER)
    authenticate_as(client, responder)
    response = client.get("/api/v1/analytics/category-breakdown")
    assert response.status_code == 403


def test_category_breakdown_counts_reports(
    client: TestClient, make_user, incident_payload
) -> None:
    citizen = make_user(UserRole.CITIZEN)
    authenticate_as(client, citizen)
    report(client, incident_payload)
    report(client, incident_payload, category="FIRE")
    report(client, incident_payload, category="FIRE")

    dispatcher = make_user(UserRole.DISPATCHER)
    authenticate_as(client, dispatcher)
    body = client.get("/api/v1/analytics/category-breakdown").json()

    assert body["total"] == 3
    by_category = {item["category"]: item["count"] for item in body["items"]}
    assert by_category["FIRE"] == 2
    assert by_category["FLOOD"] == 1
    # Every seeded incident is auto-scored, so the average must be a number,
    # not a null standing in for "nothing to average".
    fire_row = next(item for item in body["items"] if item["category"] == "FIRE")
    assert fire_row["avg_priority_score"] is not None


def test_response_time_measures_report_to_first_dispatch(
    client: TestClient, make_user, incident_payload, db_session: Session
) -> None:
    citizen = make_user(UserRole.CITIZEN)
    authenticate_as(client, citizen)
    incident = report(client, incident_payload)

    dispatcher = make_user(UserRole.DISPATCHER)
    authenticate_as(client, dispatcher)
    resource = make_resource(client)
    dispatch = client.post(
        f"/api/v1/incidents/{incident['id']}/dispatches",
        json={"resource_id": resource["id"]},
    ).json()

    # Pin both timestamps to a known 20-minute gap so the average is exact
    # rather than whatever wall-clock time the two API calls happened to take.
    base = datetime.now(UTC) - timedelta(hours=2)
    incident_row = db_session.get(Incident, uuid.UUID(incident["id"]))
    dispatch_row = db_session.get(Dispatch, uuid.UUID(dispatch["id"]))
    assert incident_row is not None and dispatch_row is not None
    incident_row.created_at = base
    dispatch_row.created_at = base + timedelta(minutes=20)
    db_session.commit()

    body = client.get("/api/v1/analytics/response-time").json()
    assert body["sample_size"] == 1
    assert body["avg_minutes"] == 20.0
    assert body["min_minutes"] == 20.0
    assert body["max_minutes"] == 20.0


def test_response_time_is_empty_before_any_dispatch(
    client: TestClient, make_user, incident_payload
) -> None:
    citizen = make_user(UserRole.CITIZEN)
    authenticate_as(client, citizen)
    report(client, incident_payload)

    dispatcher = make_user(UserRole.DISPATCHER)
    authenticate_as(client, dispatcher)
    body = client.get("/api/v1/analytics/response-time").json()
    assert body["sample_size"] == 0
    assert body["avg_minutes"] is None


def test_resolution_time_measures_report_to_resolved(
    client: TestClient, make_user, incident_payload, db_session: Session
) -> None:
    citizen = make_user(UserRole.CITIZEN)
    authenticate_as(client, citizen)
    incident = report(client, incident_payload)

    dispatcher = make_user(UserRole.DISPATCHER)
    authenticate_as(client, dispatcher)
    for target in (
        "RECEIVED",
        "UNDER_REVIEW",
        "PRIORITIZED",
        "ASSIGNED",
        "RESPONDER_EN_ROUTE",
        "ON_SCENE",
        "RESOLVED",
    ):
        response = dispatcher_status(client, incident["id"], target)
        assert response.status_code == 200, response.text

    base = datetime.now(UTC) - timedelta(hours=3)
    incident_row = db_session.get(Incident, uuid.UUID(incident["id"]))
    assert incident_row is not None
    incident_row.created_at = base
    incident_row.resolved_at = base + timedelta(minutes=90)
    db_session.commit()

    body = client.get("/api/v1/analytics/resolution-time").json()
    assert body["sample_size"] == 1
    assert body["avg_minutes"] == 90.0


def dispatcher_status(client: TestClient, incident_id: str, status_value: str):
    return client.post(
        f"/api/v1/incidents/{incident_id}/status", json={"status": status_value}
    )


def test_resource_utilization_counts_dispatches_by_type(
    client: TestClient, make_user, incident_payload
) -> None:
    citizen = make_user(UserRole.CITIZEN)
    authenticate_as(client, citizen)
    incident = report(client, incident_payload)

    dispatcher = make_user(UserRole.DISPATCHER)
    authenticate_as(client, dispatcher)
    ambulance = make_resource(client, resource_type="AMBULANCE")
    make_resource(client, resource_type="FIRE_ENGINE")
    client.post(
        f"/api/v1/incidents/{incident['id']}/dispatches",
        json={"resource_id": ambulance["id"]},
    )

    body = client.get("/api/v1/analytics/resource-utilization").json()
    by_type = {item["resource_type"]: item for item in body["items"]}
    assert by_type["AMBULANCE"]["total_resources"] == 1
    assert by_type["AMBULANCE"]["dispatches_in_period"] == 1
    assert by_type["FIRE_ENGINE"]["dispatches_in_period"] == 0


def test_hotspots_never_return_a_raw_incident_coordinate(
    client: TestClient, make_user, incident_payload
) -> None:
    """The rule this endpoint exists to enforce (CLAUDE.md section 5)."""
    citizen = make_user(UserRole.CITIZEN)
    authenticate_as(client, citizen)
    # Two reports close together but not identical, inside the same ~1km cell.
    report(client, incident_payload, latitude=13.0827, longitude=80.2707)
    report(client, incident_payload, latitude=13.0831, longitude=80.2711)

    dispatcher = make_user(UserRole.DISPATCHER)
    authenticate_as(client, dispatcher)
    body = client.get("/api/v1/analytics/hotspots").json()

    assert body["cell_size_degrees"] == 0.01
    assert len(body["items"]) == 1
    cell = body["items"][0]
    assert cell["incident_count"] == 2
    # The cell centre is a rounded multiple of the grid size, and matches
    # neither reported point exactly.
    assert cell["latitude"] not in (13.0827, 13.0831)
    assert cell["longitude"] not in (80.2707, 80.2711)
    assert round(cell["latitude"] / 0.01) * 0.01 == cell["latitude"]


def test_hotspots_can_be_filtered_by_category(
    client: TestClient, make_user, incident_payload
) -> None:
    citizen = make_user(UserRole.CITIZEN)
    authenticate_as(client, citizen)
    report(client, incident_payload, category="FLOOD")
    report(client, incident_payload, category="FIRE", latitude=13.05, longitude=80.20)

    dispatcher = make_user(UserRole.DISPATCHER)
    authenticate_as(client, dispatcher)
    body = client.get("/api/v1/analytics/hotspots", params={"category": "FIRE"}).json()
    assert len(body["items"]) == 1
    assert body["items"][0]["incident_count"] == 1
