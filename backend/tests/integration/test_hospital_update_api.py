"""Administrators correct what a hospital is; capacity stays the operator's business."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.enums import UserRole
from app.models.incident import AuditLog
from tests.integration.test_hospitals_api import (
    CHENNAI,
    authenticate_as,
    make_hospital,
    notify,
    report,
)

MUMBAI = (19.0760, 72.8777)


@pytest.fixture
def setting(as_role, incident_payload, make_user):
    citizen, _ = as_role(UserRole.CITIZEN)
    incident = report(citizen, incident_payload)
    admin_client, admin = as_role(UserRole.ADMIN)
    operator = make_user(UserRole.HOSPITAL_OPERATOR)
    hospital = make_hospital(admin_client, managed_by_id=str(operator.id))
    # as_role hands back one shared HTTP client, so each test re-authenticates
    # explicitly whenever it switches who is speaking.
    return {
        "client": admin_client,
        "admin": admin,
        "operator": operator,
        "incident": incident,
        "hospital": hospital,
    }


def as_admin(setting):
    return authenticate_as(setting["client"], setting["admin"])


def patch(setting, body: dict, client=None):
    return (client or setting["client"]).patch(
        f"/api/v1/hospitals/{setting['hospital']['id']}", json=body
    )


def test_an_admin_corrects_the_details(setting) -> None:
    response = patch(
        setting,
        {
            "name": "Government General Hospital",
            "address": "Park Town, Chennai",
            "contact_phone": "+91 44 2530 5000",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Government General Hospital"
    assert body["address"] == "Park Town, Chennai"
    assert body["contact_phone"] == "+91 44 2530 5000"
    assert body["code"] == "GH-01"
    assert body["available_beds"] == 12  # capacity untouched


def test_moving_a_hospital_moves_where_searches_find_it(setting) -> None:
    nearby = "/api/v1/hospitals/nearby?latitude={}&longitude={}&radius_km=20"
    assert (
        patch(setting, {"latitude": MUMBAI[0], "longitude": MUMBAI[1]}).status_code == 200
    )

    old_place = setting["client"].get(nearby.format(*CHENNAI)).json()
    new_place = setting["client"].get(nearby.format(*MUMBAI)).json()
    assert old_place["count"] == 0
    assert [h["code"] for h in new_place["items"]] == ["GH-01"]


def test_position_must_be_given_as_a_pair(setting) -> None:
    assert patch(setting, {"latitude": 12.9}).status_code == 400


def test_the_code_and_the_capacity_are_not_editable_here(setting) -> None:
    for body in (
        {"code": "NEW-1"},
        {"available_beds": 99},
        {"accepting_emergencies": False},
    ):
        assert patch(setting, body).status_code == 400, body
    assert patch(setting, {}).status_code == 400
    assert patch(setting, {"name": None}).status_code == 400


def test_the_linked_operator_can_be_changed_and_removed(setting, make_user) -> None:
    other = make_user(UserRole.HOSPITAL_OPERATOR)
    assert patch(setting, {"managed_by_id": str(other.id)}).json()["managed_by"][
        "id"
    ] == str(other.id)

    unlinked = patch(setting, {"managed_by_id": None})
    assert unlinked.status_code == 200 and unlinked.json()["managed_by"] is None
    # The previous operator can no longer maintain it.
    old = authenticate_as(setting["client"], setting["operator"])
    refused = old.post(
        f"/api/v1/hospitals/{setting['hospital']['id']}/capacity",
        json={"available_beds": 1},
    )
    assert refused.status_code == 403


def test_only_a_hospital_operator_or_admin_can_be_linked(setting, make_user) -> None:
    for role in (UserRole.CITIZEN, UserRole.RESPONDER):
        assert (
            patch(setting, {"managed_by_id": str(make_user(role).id)}).status_code == 400
        )


@pytest.mark.parametrize(
    "role",
    [
        UserRole.DISPATCHER,
        UserRole.HOSPITAL_OPERATOR,
        UserRole.RESPONDER,
        UserRole.CITIZEN,
    ],
)
def test_only_administrators_may_edit(setting, as_role, role) -> None:
    client, _ = as_role(role)
    assert patch(setting, {"name": "Hijacked"}, client).status_code == 403
    assert (
        as_admin(setting)
        .get(f"/api/v1/hospitals/{setting['hospital']['id']}")
        .json()["name"]
        != "Hijacked"
    )


def test_the_operator_of_this_very_hospital_cannot_rename_it(
    setting,
) -> None:
    client = authenticate_as(setting["client"], setting["operator"])
    assert patch(setting, {"name": "Mine now"}, client).status_code == 403


def test_editing_requires_a_login(setting, client) -> None:
    client.headers.pop("Authorization", None)
    response = client.patch(
        f"/api/v1/hospitals/{setting['hospital']['id']}", json={"name": "No"}
    )
    assert response.status_code == 401


def test_an_unknown_hospital_is_404(setting) -> None:
    response = setting["client"].patch(
        "/api/v1/hospitals/00000000-0000-0000-0000-000000000000", json={"name": "Nowhere"}
    )
    assert response.status_code == 404


def test_a_hospital_with_open_notices_cannot_be_retired(setting) -> None:
    notice = notify(setting)
    refused = patch(setting, {"is_active": False})
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "HOSPITAL_HAS_OPEN_NOTICES"

    operator = authenticate_as(setting["client"], setting["operator"])
    operator.post(
        f"/api/v1/hospital-notices/{notice['id']}/status",
        json={"status": "DIVERTED", "response_note": "Closing the department."},
    )
    admin = authenticate_as(setting["client"], setting["admin"])
    retired = patch(setting, {"is_active": False}, admin)
    assert retired.status_code == 200 and retired.json()["is_active"] is False

    listed = admin.get("/api/v1/hospitals").json()["items"]
    assert setting["hospital"]["id"] not in [h["id"] for h in listed]
    assert patch(setting, {"is_active": True}, admin).json()["is_active"] is True


def test_the_audit_log_records_which_fields_changed_never_their_values(
    setting, db_session
) -> None:
    patch(setting, {"contact_phone": "+91 99999 00000", "address": "Secret Lane 7"})
    rows = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "hospital.updated")
    ).all()
    assert len(rows) == 1
    assert rows[0].event_metadata == {"fields": ["address", "contact_phone"]}
    assert "99999" not in str(rows[0].event_metadata)
