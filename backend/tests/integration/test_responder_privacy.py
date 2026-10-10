"""A responder works from their assignments, not from the incident queue.

docs/SECURITY.md section 3: a responder sees the assignments dispatched to a unit
they operate, through a scene brief that omits the reporter. They cannot browse
incident records, the map feed, media or analyses. This is the least-privilege
counterpart of ``test_hospital_operator_privacy.py``: a crew member's phone is the
device most likely to be lost, so it should hold the least.
"""

from __future__ import annotations

import pytest

from app.models.enums import UserRole
from tests.integration.test_dispatch_api import (
    authenticate_as,
    dispatch_unit,
    scene,  # noqa: F401  (fixture)
)


@pytest.fixture
def responder_client(scene):  # noqa: F811
    dispatch_unit(scene)
    return authenticate_as(scene["client"], scene["responder"])


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/incidents",
        "/api/v1/incidents/stats/summary",
        "/api/v1/geo/incidents/nearby?latitude=13.08&longitude=80.27&radius_km=5",
        "/api/v1/geo/incidents/bbox?min_lat=12&min_lon=79&max_lat=14&max_lon=81",
    ],
)
def test_incident_collections_are_closed_to_a_responder(
    responder_client, path: str
) -> None:
    assert responder_client.get(path).status_code == 403


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
def test_a_single_incident_is_not_readable_by_a_responder(
    scene, responder_client, suffix: str  # noqa: F811
) -> None:
    incident = scene["incident"]
    response = responder_client.get(f"/api/v1/incidents/{incident['id']}{suffix}")
    assert response.status_code in (403, 404), (suffix, response.status_code)
    assert incident["description"] not in response.text
    assert incident["reference_code"] not in response.text


def test_a_responder_cannot_ask_for_an_ai_analysis(
    scene, responder_client  # noqa: F811
) -> None:
    response = responder_client.post(
        f"/api/v1/incidents/{scene['incident']['id']}/analyses"
    )
    assert response.status_code in (403, 404)


def test_a_responder_cannot_reach_the_priority_or_status_controls(
    scene, responder_client, as_role  # noqa: F811
) -> None:
    incident_id = scene["incident"]["id"]
    base = f"/api/v1/incidents/{incident_id}"
    # Status is open to the reporter, so a non-reader is told the incident does not
    # exist (404) rather than that it does (403); the other two are dispatch-only.
    status = responder_client.post(f"{base}/status", json={"status": "RECEIVED"})
    assert status.status_code in (403, 404)
    assert responder_client.post(f"{base}/priority", json={}).status_code == 403
    assert responder_client.post(f"{base}/assign", json={}).status_code == 403

    # Nothing moved: the dispatcher still sees the status the citizen created.
    # (the responder client shares the scene's HTTP client, so use a fresh one)
    dispatcher, _ = as_role(UserRole.DISPATCHER)
    assert dispatcher.get(base).json()["status"] == scene["incident"]["status"]


def test_the_responders_own_work_still_functions(
    scene, responder_client  # noqa: F811
) -> None:
    """Everything the responder application calls keeps working."""
    assignments = responder_client.get("/api/v1/dispatches/mine")
    assert assignments.status_code == 200 and len(assignments.json()) == 1
    dispatch = assignments.json()[0]

    detail = responder_client.get(f"/api/v1/dispatches/{dispatch['id']}")
    assert detail.status_code == 200
    assert not set(detail.json()["incident"]) & {"reported_by", "reporter", "reporter_id"}

    moved = responder_client.post(
        f"/api/v1/dispatches/{dispatch['id']}/status", json={"status": "EN_ROUTE"}
    )
    assert moved.status_code == 200, moved.text
    assert responder_client.get("/api/v1/notifications").status_code == 200
    assert responder_client.get("/api/v1/auth/me").status_code == 200


def test_closing_the_assignment_does_not_widen_what_a_responder_may_read(
    scene, responder_client  # noqa: F811
) -> None:
    dispatch = responder_client.get("/api/v1/dispatches/mine").json()[0]
    for next_status in ("EN_ROUTE", "ON_SCENE", "COMPLETED"):
        response = responder_client.post(
            f"/api/v1/dispatches/{dispatch['id']}/status", json={"status": next_status}
        )
        assert response.status_code == 200, (next_status, response.text)
    incident_id = scene["incident"]["id"]
    assert responder_client.get(f"/api/v1/incidents/{incident_id}").status_code in (
        403,
        404,
    )


def test_the_dispatch_side_is_unaffected(scene, as_role) -> None:  # noqa: F811
    incident_id = scene["incident"]["id"]
    for role in (UserRole.DISPATCHER, UserRole.ADMIN):
        client, _ = as_role(role)
        assert client.get(f"/api/v1/incidents/{incident_id}").status_code == 200, role
        assert client.get("/api/v1/incidents").status_code == 200, role
