"""Notifications (Phase 13).

Two properties under test: a notification reaches exactly one inbox — its
recipient's — and a channel this deployment cannot send on says so rather
than going quietly nowhere.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.enums import UserRole


def report(client: TestClient, payload: dict, **overrides: object) -> dict:
    response = client.post("/api/v1/incidents", json=payload | overrides)
    assert response.status_code == 201, response.text
    return response.json()


def authenticate_as(client: TestClient, user) -> TestClient:
    token, _ = create_access_token(user.id, user.role.value)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def test_a_reporter_is_told_when_their_report_moves(
    client: TestClient, make_user, incident_payload
) -> None:
    citizen = make_user(UserRole.CITIZEN)
    dispatcher = make_user(UserRole.DISPATCHER)

    authenticate_as(client, citizen)
    incident = report(client, incident_payload)
    assert client.get("/api/v1/notifications").json()["total"] == 0

    authenticate_as(client, dispatcher)
    client.post(
        f"/api/v1/incidents/{incident['id']}/status", json={"status": "UNDER_REVIEW"}
    )

    authenticate_as(client, citizen)
    body = client.get("/api/v1/notifications").json()
    assert body["total"] == 1
    assert body["items"][0]["kind"] == "INCIDENT_STATUS_CHANGED"
    assert "reviewing" in body["items"][0]["body"]


def test_nobody_is_told_about_their_own_action(
    client: TestClient, make_user, incident_payload
) -> None:
    """A citizen cancelling their own report does not need telling they did."""
    citizen = make_user(UserRole.CITIZEN)
    authenticate_as(client, citizen)
    incident = report(client, incident_payload)
    client.post(
        f"/api/v1/incidents/{incident['id']}/status", json={"status": "CANCELLED"}
    )

    assert client.get("/api/v1/notifications").json()["total"] == 0


def test_a_notification_reaches_only_its_recipient(
    client: TestClient, make_user, incident_payload
) -> None:
    citizen = make_user(UserRole.CITIZEN)
    other = make_user(UserRole.CITIZEN)
    dispatcher = make_user(UserRole.DISPATCHER)

    authenticate_as(client, citizen)
    incident = report(client, incident_payload)
    authenticate_as(client, dispatcher)
    client.post(f"/api/v1/incidents/{incident['id']}/status", json={"status": "RECEIVED"})

    authenticate_as(client, other)
    assert client.get("/api/v1/notifications").json()["total"] == 0


def test_a_crew_is_told_when_their_unit_is_dispatched(
    client: TestClient, make_user, incident_payload
) -> None:
    citizen = make_user(UserRole.CITIZEN)
    dispatcher = make_user(UserRole.DISPATCHER)
    responder = make_user(UserRole.RESPONDER)

    authenticate_as(client, citizen)
    incident = report(client, incident_payload)

    authenticate_as(client, dispatcher)
    resource = client.post(
        "/api/v1/resources",
        json={
            "call_sign": "AMB-07",
            "name": "Ambulance 7",
            "resource_type": "AMBULANCE",
            "latitude": 13.0827,
            "longitude": 80.2707,
            "operator_id": str(responder.id),
        },
    ).json()
    client.post(
        f"/api/v1/incidents/{incident['id']}/dispatches",
        json={"resource_id": resource["id"]},
    )

    authenticate_as(client, responder)
    body = client.get("/api/v1/notifications").json()
    assert body["total"] == 1
    assert body["items"][0]["kind"] == "DISPATCH_ASSIGNED"
    assert body["items"][0]["dispatch_id"] is not None


def test_an_unconfigured_channel_is_recorded_not_silently_dropped(
    client: TestClient, make_user, incident_payload, db_session: Session
) -> None:
    """CLAUDE.md's rule for AI applies here too: fail visibly, not quietly."""
    citizen = make_user(UserRole.CITIZEN)
    # Committed, not just set in memory: the SMS channel is only attempted for
    # a recipient the *database* says has a number.
    citizen.phone = "+919876543210"
    db_session.commit()
    dispatcher = make_user(UserRole.DISPATCHER)

    authenticate_as(client, citizen)
    incident = report(client, incident_payload)
    authenticate_as(client, dispatcher)
    client.post(f"/api/v1/incidents/{incident['id']}/status", json={"status": "RECEIVED"})

    authenticate_as(client, citizen)
    deliveries = client.get("/api/v1/notifications").json()["items"][0]["deliveries"]
    by_channel = {row["channel"]: row for row in deliveries}

    assert by_channel["IN_APP"]["status"] == "DELIVERED"
    # The SMS was attempted and could not be sent — and the record says so.
    assert by_channel["SMS"]["status"] == "UNAVAILABLE"
    assert "no sms provider" in by_channel["SMS"]["detail"].lower()


def test_marking_one_as_read(client: TestClient, make_user, incident_payload) -> None:
    citizen = make_user(UserRole.CITIZEN)
    dispatcher = make_user(UserRole.DISPATCHER)
    authenticate_as(client, citizen)
    incident = report(client, incident_payload)
    authenticate_as(client, dispatcher)
    client.post(f"/api/v1/incidents/{incident['id']}/status", json={"status": "RECEIVED"})

    authenticate_as(client, citizen)
    assert client.get("/api/v1/notifications/unread-count").json()["unread"] == 1

    notification = client.get("/api/v1/notifications").json()["items"][0]
    response = client.post(f"/api/v1/notifications/{notification['id']}/read")
    assert response.status_code == 200
    assert response.json()["read_at"] is not None
    assert client.get("/api/v1/notifications/unread-count").json()["unread"] == 0


def test_marking_everything_as_read(
    client: TestClient, make_user, incident_payload
) -> None:
    citizen = make_user(UserRole.CITIZEN)
    dispatcher = make_user(UserRole.DISPATCHER)
    authenticate_as(client, citizen)
    incident = report(client, incident_payload)
    authenticate_as(client, dispatcher)
    for status in ("RECEIVED", "UNDER_REVIEW"):
        client.post(f"/api/v1/incidents/{incident['id']}/status", json={"status": status})

    authenticate_as(client, citizen)
    assert client.get("/api/v1/notifications/unread-count").json()["unread"] == 2
    client.post("/api/v1/notifications/read-all")
    assert client.get("/api/v1/notifications/unread-count").json()["unread"] == 0


def test_someone_elses_notification_reads_as_absent(
    client: TestClient, make_user, incident_payload
) -> None:
    citizen = make_user(UserRole.CITIZEN)
    dispatcher = make_user(UserRole.DISPATCHER)
    stranger = make_user(UserRole.CITIZEN)

    authenticate_as(client, citizen)
    incident = report(client, incident_payload)
    authenticate_as(client, dispatcher)
    client.post(f"/api/v1/incidents/{incident['id']}/status", json={"status": "RECEIVED"})

    authenticate_as(client, citizen)
    notification = client.get("/api/v1/notifications").json()["items"][0]

    authenticate_as(client, stranger)
    response = client.post(f"/api/v1/notifications/{notification['id']}/read")
    assert response.status_code == 404


def test_the_inbox_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/notifications").status_code == 401


def test_a_notification_carries_no_location_or_contact_detail(
    client: TestClient, make_user, incident_payload
) -> None:
    citizen = make_user(UserRole.CITIZEN)
    dispatcher = make_user(UserRole.DISPATCHER)
    authenticate_as(client, citizen)
    incident = report(client, incident_payload)
    authenticate_as(client, dispatcher)
    client.post(f"/api/v1/incidents/{incident['id']}/status", json={"status": "RECEIVED"})

    authenticate_as(client, citizen)
    item = client.get("/api/v1/notifications").json()["items"][0]
    assert not set(item.get("context") or {}) & {
        "latitude",
        "longitude",
        "contact_phone",
    }
