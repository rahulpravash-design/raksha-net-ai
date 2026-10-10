"""A hospital operator reads hospital data, not incident records.

docs/SECURITY.md section 3: "a hospital operator sees the clinical and ETA
information relevant to an inbound patient, not the reporter's contact details."
Before this module the role was grouped with the other operational roles and so
could read every incident — reporter, report text and exact position included.
"""

from __future__ import annotations

import pytest

from app.models.enums import (
    INCIDENT_VIEW_ROLES,
    OPERATIONAL_ROLES,
    UserRole,
)
from tests.integration.test_hospitals_api import (
    authenticate_as,
    make_hospital,
    notify,
    report,
)


def test_the_role_sets_are_what_the_docs_describe() -> None:
    assert UserRole.HOSPITAL_OPERATOR in OPERATIONAL_ROLES
    assert UserRole.HOSPITAL_OPERATOR not in INCIDENT_VIEW_ROLES
    assert OPERATIONAL_ROLES - {UserRole.HOSPITAL_OPERATOR} == INCIDENT_VIEW_ROLES
    assert UserRole.DISPATCHER in INCIDENT_VIEW_ROLES
    assert UserRole.RESPONDER in INCIDENT_VIEW_ROLES


@pytest.fixture
def world(as_role, incident_payload, make_user):
    citizen, _ = as_role(UserRole.CITIZEN)
    incident = report(citizen, incident_payload)
    admin_client, _ = as_role(UserRole.ADMIN)
    operator = make_user(UserRole.HOSPITAL_OPERATOR)
    hospital = make_hospital(admin_client, managed_by_id=str(operator.id))
    setting = {
        "client": admin_client,
        "operator": operator,
        "incident": incident,
        "hospital": hospital,
    }
    notify(setting)
    return setting


@pytest.fixture
def operator_client(world):
    return authenticate_as(world["client"], world["operator"])


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/incidents",
        "/api/v1/incidents/stats/summary",
        "/api/v1/geo/incidents/nearby?latitude=13.08&longitude=80.27&radius_km=5",
        "/api/v1/geo/incidents/bbox?min_lat=12&min_lon=79&max_lat=14&max_lon=81",
    ],
)
def test_incident_collections_are_closed_to_a_hospital_operator(
    operator_client, path: str
) -> None:
    assert operator_client.get(path).status_code == 403


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "/history",
        "/media",
        "/analyses",
        "/dispatches",
        "/hospital-notices",
        "/resource-recommendations",
    ],
)
def test_a_single_incident_is_not_readable_by_a_hospital_operator(
    world, operator_client, suffix: str
) -> None:
    response = operator_client.get(f"/api/v1/incidents/{world['incident']['id']}{suffix}")
    assert response.status_code in (403, 404), (suffix, response.status_code)
    text = response.text
    assert world["incident"]["description"] not in text
    assert "Test Person" not in text


def test_the_operator_cannot_ask_for_an_ai_analysis_of_an_incident(
    world, operator_client
) -> None:
    response = operator_client.post(
        f"/api/v1/incidents/{world['incident']['id']}/analyses"
    )
    assert response.status_code in (403, 404)


def test_the_hospital_operators_own_work_still_functions(world, operator_client) -> None:
    hospital_id = world["hospital"]["id"]
    assert operator_client.get("/api/v1/hospitals").status_code == 200
    notices = operator_client.get(f"/api/v1/hospitals/{hospital_id}/notices")
    assert notices.status_code == 200 and len(notices.json()) == 1
    capacity = operator_client.post(
        f"/api/v1/hospitals/{hospital_id}/capacity", json={"available_beds": 5}
    )
    assert capacity.status_code == 200


def test_dispatchers_and_responders_keep_incident_access(world, as_role) -> None:
    for role in (UserRole.DISPATCHER, UserRole.RESPONDER, UserRole.ADMIN):
        client, _ = as_role(role)
        response = client.get(f"/api/v1/incidents/{world['incident']['id']}")
        assert response.status_code == 200, role
