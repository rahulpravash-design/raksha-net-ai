"""Hospital capacity and inbound-patient notices (Phase 12).

The property under test throughout: a hospital learns what it needs to prepare
a bed, and nothing about the person who reported the incident.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.models.enums import UserRole

CHENNAI = (13.0827, 80.2707)


def report(client: TestClient, payload: dict, **overrides: object) -> dict:
    response = client.post("/api/v1/incidents", json=payload | overrides)
    assert response.status_code == 201, response.text
    return response.json()


def authenticate_as(client: TestClient, user) -> TestClient:
    token, _ = create_access_token(user.id, user.role.value)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def make_hospital(client: TestClient, **overrides: object) -> dict:
    payload = {
        "code": "GH-01",
        "name": "General Hospital, Chennai",
        "latitude": CHENNAI[0],
        "longitude": CHENNAI[1],
        "total_beds": 100,
        "available_beds": 12,
        "icu_total": 20,
        "icu_available": 3,
        "specialties": ["trauma", "burns"],
    }
    payload.update(overrides)
    response = client.post("/api/v1/hospitals", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def setting(as_role, incident_payload, make_user):
    citizen, _ = as_role(UserRole.CITIZEN)
    incident = report(citizen, incident_payload)

    admin_client, admin = as_role(UserRole.ADMIN)
    operator = make_user(UserRole.HOSPITAL_OPERATOR)
    hospital = make_hospital(admin_client, managed_by_id=str(operator.id))
    return {
        "client": admin_client,
        "admin": admin,
        "operator": operator,
        "incident": incident,
        "hospital": hospital,
    }


# --- registration and capacity -----------------------------------------------
def test_an_admin_can_register_a_hospital(setting) -> None:
    assert setting["hospital"]["code"] == "GH-01"
    assert setting["hospital"]["available_beds"] == 12


def test_a_dispatcher_cannot_register_a_hospital(as_role) -> None:
    client, _ = as_role(UserRole.DISPATCHER)
    response = client.post(
        "/api/v1/hospitals",
        json={
            "code": "X-1",
            "name": "Unauthorised",
            "latitude": CHENNAI[0],
            "longitude": CHENNAI[1],
        },
    )
    assert response.status_code == 403


def test_available_beds_cannot_exceed_the_total(as_role) -> None:
    client, _ = as_role(UserRole.ADMIN)
    response = client.post(
        "/api/v1/hospitals",
        json={
            "code": "BAD-1",
            "name": "Impossible",
            "latitude": CHENNAI[0],
            "longitude": CHENNAI[1],
            "total_beds": 5,
            "available_beds": 50,
        },
    )
    assert response.status_code == 400


def test_the_operator_maintains_their_own_hospitals_capacity(setting) -> None:
    client = authenticate_as(setting["client"], setting["operator"])
    response = client.post(
        f"/api/v1/hospitals/{setting['hospital']['id']}/capacity",
        json={"available_beds": 4, "icu_available": 1, "accepting_emergencies": False},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available_beds"] == 4
    assert body["accepting_emergencies"] is False
    assert body["capacity_updated_at"] is not None


def test_an_operator_cannot_update_someone_elses_hospital(setting, as_role) -> None:
    stranger, _ = as_role(UserRole.HOSPITAL_OPERATOR)
    response = stranger.post(
        f"/api/v1/hospitals/{setting['hospital']['id']}/capacity",
        json={"available_beds": 0},
    )
    assert response.status_code == 403


def test_capacity_cannot_be_reported_above_the_total(setting) -> None:
    client = authenticate_as(setting["client"], setting["operator"])
    response = client.post(
        f"/api/v1/hospitals/{setting['hospital']['id']}/capacity",
        json={"available_beds": 9999},
    )
    assert response.status_code == 400


# --- finding a receiving facility --------------------------------------------
def test_nearby_excludes_a_hospital_with_no_free_bed(setting) -> None:
    """A full hospital is not a nearby hospital."""
    client = authenticate_as(setting["client"], setting["operator"])
    client.post(
        f"/api/v1/hospitals/{setting['hospital']['id']}/capacity",
        json={"available_beds": 0},
    )

    dispatcher = authenticate_as(client, setting["admin"])
    body = dispatcher.get(
        "/api/v1/hospitals/nearby",
        params={"latitude": CHENNAI[0], "longitude": CHENNAI[1], "radius_km": 20},
    ).json()
    assert body["count"] == 0


def test_nearby_can_require_an_icu_bed(setting) -> None:
    client = authenticate_as(setting["client"], setting["operator"])
    client.post(
        f"/api/v1/hospitals/{setting['hospital']['id']}/capacity",
        json={"icu_available": 0},
    )

    dispatcher = authenticate_as(client, setting["admin"])
    body = dispatcher.get(
        "/api/v1/hospitals/nearby",
        params={
            "latitude": CHENNAI[0],
            "longitude": CHENNAI[1],
            "radius_km": 20,
            "needs_icu": True,
        },
    ).json()
    assert body["count"] == 0


def test_a_citizen_cannot_browse_hospitals(as_role) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    assert client.get("/api/v1/hospitals").status_code == 403


# --- inbound patient notices --------------------------------------------------
def notify(setting, **overrides: object) -> dict:
    payload = {
        "hospital_id": setting["hospital"]["id"],
        "patient_count": 3,
        "severity": "CRITICAL",
        "eta_minutes": 8,
        "clinical_notes": "Two with suspected smoke inhalation.",
    }
    payload.update(overrides)
    response = setting["client"].post(
        f"/api/v1/incidents/{setting['incident']['id']}/hospital-notices", json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_a_dispatcher_can_notify_a_hospital(setting) -> None:
    body = notify(setting)
    assert body["status"] == "NOTIFIED"
    assert body["patient_count"] == 3
    assert body["category"] == "FLOOD"


def test_the_notice_carries_nothing_about_the_reporter(setting) -> None:
    """Data minimisation, enforced by the shape of the response itself."""
    body = notify(setting)

    leaky = {
        "reported_by",
        "reported_by_id",
        "reporter",
        "contact_phone",
        "description",
        "latitude",
        "longitude",
        "address_text",
    }
    assert not set(body) & leaky


def test_a_hospital_operator_sees_their_inbound_patients(setting) -> None:
    notify(setting)
    client = authenticate_as(setting["client"], setting["operator"])

    rows = client.get(f"/api/v1/hospitals/{setting['hospital']['id']}/notices").json()
    assert len(rows) == 1
    assert rows[0]["eta_minutes"] == 8


def test_another_hospitals_operator_sees_nothing(setting, as_role) -> None:
    notify(setting)
    stranger, _ = as_role(UserRole.HOSPITAL_OPERATOR)
    response = stranger.get(f"/api/v1/hospitals/{setting['hospital']['id']}/notices")
    assert response.status_code == 404


def test_the_hospital_can_acknowledge(setting) -> None:
    notice = notify(setting)
    client = authenticate_as(setting["client"], setting["operator"])

    response = client.post(
        f"/api/v1/hospital-notices/{notice['id']}/status",
        json={"status": "ACKNOWLEDGED", "response_note": "Two bays ready."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ACKNOWLEDGED"
    assert response.json()["acknowledged_at"] is not None


def test_diverting_requires_a_note(setting) -> None:
    notice = notify(setting)
    client = authenticate_as(setting["client"], setting["operator"])

    bad = client.post(
        f"/api/v1/hospital-notices/{notice['id']}/status", json={"status": "DIVERTED"}
    )
    assert bad.status_code == 400

    good = client.post(
        f"/api/v1/hospital-notices/{notice['id']}/status",
        json={"status": "DIVERTED", "response_note": "Resus full; try GH-02."},
    )
    assert good.status_code == 200


def test_an_illegal_notice_transition_is_refused(setting) -> None:
    notice = notify(setting)
    client = authenticate_as(setting["client"], setting["operator"])
    response = client.post(
        f"/api/v1/hospital-notices/{notice['id']}/status", json={"status": "ARRIVED"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOTICE_INVALID_TRANSITION"


def test_a_citizen_cannot_notify_a_hospital(setting, as_role) -> None:
    citizen, _ = as_role(UserRole.CITIZEN)
    response = citizen.post(
        f"/api/v1/incidents/{setting['incident']['id']}/hospital-notices",
        json={"hospital_id": setting["hospital"]["id"]},
    )
    assert response.status_code == 403


def test_notifying_an_unknown_hospital_is_404(setting) -> None:
    response = setting["client"].post(
        f"/api/v1/incidents/{setting['incident']['id']}/hospital-notices",
        json={"hospital_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404


def test_an_incident_lists_the_hospitals_it_notified(setting) -> None:
    notify(setting)
    rows = (
        setting["client"]
        .get(f"/api/v1/incidents/{setting['incident']['id']}/hospital-notices")
        .json()
    )
    assert len(rows) == 1
