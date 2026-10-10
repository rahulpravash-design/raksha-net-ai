"""Rate limits as a client meets them. The rest of the suite switches them off."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.enums import UserRole


@pytest.fixture
def limits_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)


def authenticate_as(client: TestClient, user) -> None:
    token, _ = create_access_token(user.id, user.role.value)
    client.headers["Authorization"] = f"Bearer {token}"


def test_repeated_sign_in_attempts_are_throttled(client: TestClient, limits_on) -> None:
    body = {"email": "nobody@example.org", "password": "not-the-password-xx"}
    statuses = [
        client.post("/api/v1/auth/login", json=body).status_code for _ in range(11)
    ]

    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429


def test_a_throttled_response_is_the_standard_envelope_with_retry_after(
    client: TestClient, limits_on
) -> None:
    body = {"email": "nobody@example.org", "password": "not-the-password-xx"}
    for _ in range(10):
        client.post("/api/v1/auth/login", json=body)
    response = client.post("/api/v1/auth/login", json=body)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert 1 <= int(response.headers["Retry-After"]) <= 60


def test_the_general_api_has_a_backstop_limit(
    client: TestClient, limits_on, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_default_per_minute", 3)
    statuses = [client.get("/api/v1/auth/me").status_code for _ in range(5)]
    assert statuses[:3] == [401, 401, 401]
    assert statuses[3:] == [429, 429]


def test_health_probes_are_never_throttled(
    client: TestClient, limits_on, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_default_per_minute", 1)
    client.get("/api/v1/auth/me")  # uses the one allowed request
    assert all(client.get("/api/v1/health").status_code == 200 for _ in range(5))


def test_reports_are_limited_per_user_not_globally(
    client: TestClient, make_user, incident_payload, limits_on
) -> None:
    first, second = make_user(UserRole.CITIZEN), make_user(UserRole.CITIZEN)

    authenticate_as(client, first)
    statuses = [
        client.post("/api/v1/incidents", json=incident_payload).status_code
        for _ in range(13)
    ]
    assert statuses[:12] == [201] * 12
    assert statuses[12] == 429

    authenticate_as(client, second)  # a different person is unaffected
    assert client.post("/api/v1/incidents", json=incident_payload).status_code == 201


def test_limits_are_off_when_disabled(client: TestClient) -> None:
    body = {"email": "nobody@example.org", "password": "not-the-password-xx"}
    assert all(
        client.post("/api/v1/auth/login", json=body).status_code == 401 for _ in range(15)
    )
