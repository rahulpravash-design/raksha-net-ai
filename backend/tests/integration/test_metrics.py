"""The metrics endpoint: access control, content, and series cardinality."""

from __future__ import annotations

import re
import uuid

import pytest
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.enums import UserRole

TOKEN = "scrape-token-for-tests-0123456789"


@pytest.fixture
def scraping(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(get_settings(), "metrics_token", SecretStr(TOKEN))


def scrape(client: TestClient, token: str | None = TOKEN):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get("/metrics", headers=headers)


def sample(body: str, name: str, **labels: str) -> float:
    """The value of one sample, or 0.0 if that series does not exist yet."""
    for family in text_string_to_metric_families(body):
        for s in family.samples:
            if s.name == name and all(s.labels.get(k) == v for k, v in labels.items()):
                return s.value
    return 0.0


# --- access ------------------------------------------------------------------
def test_metrics_do_not_exist_unless_a_token_is_configured(client: TestClient) -> None:
    assert client.get("/metrics").status_code == 404
    assert (
        client.get("/metrics", headers={"Authorization": "Bearer anything"}).status_code
        == 404
    )


def test_metrics_need_the_token(client: TestClient, scraping) -> None:
    assert scrape(client, None).status_code == 401
    assert scrape(client, "the-wrong-token").status_code == 401


def test_a_user_session_is_not_a_scrape_token(
    client: TestClient, scraping, make_user
) -> None:
    """An administrator's access token must not read operational metrics."""
    admin = make_user(UserRole.ADMIN)
    jwt, _ = create_access_token(admin.id, admin.role.value)
    assert scrape(client, jwt).status_code == 401


def test_the_right_token_returns_prometheus_text(client: TestClient, scraping) -> None:
    response = scrape(client)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "raksha_http_requests_total" in response.text


def test_metrics_are_not_listed_in_the_public_api_schema(client: TestClient) -> None:
    assert "/metrics" not in client.get("/openapi.json").json()["paths"]


# --- content -----------------------------------------------------------------
def test_requests_are_counted_by_route_template_not_raw_path(
    client: TestClient, scraping, make_user
) -> None:
    """Otherwise every incident id would become its own time series."""
    admin = make_user(UserRole.ADMIN)
    jwt, _ = create_access_token(admin.id, admin.role.value)
    for _ in range(3):
        client.get(
            f"/api/v1/incidents/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {jwt}"},
        )

    body = scrape(client).text
    assert 'route="/api/v1/incidents/{incident_id}"' in body
    assert not re.search(r'route="[^"]*[0-9a-f]{8}-[0-9a-f]{4}-', body)
    assert (
        sample(
            body,
            "raksha_http_requests_total",
            route="/api/v1/incidents/{incident_id}",
            status="404",
        )
        >= 3
    )


def test_unknown_paths_share_one_label(client: TestClient, scraping) -> None:
    """A scanner probing random URLs must not be able to grow the series count."""
    for i in range(5):
        client.get(f"/no/such/page/{i}-{uuid.uuid4().hex}")
    body = scrape(client).text
    assert 'route="unmatched"' in body
    assert "/no/such/page" not in body


def test_latency_is_a_histogram(client: TestClient, scraping) -> None:
    client.get("/")
    body = scrape(client).text
    assert "raksha_http_request_duration_seconds_bucket" in body
    assert sample(body, "raksha_http_request_duration_seconds_count", route="/") >= 1


def test_the_scrape_itself_is_not_counted(client: TestClient, scraping) -> None:
    scrape(client)
    assert 'route="/metrics"' not in scrape(client).text


def test_queue_depth_gauges_reflect_open_incidents(
    client: TestClient, scraping, make_user, incident_payload
) -> None:
    citizen = make_user(UserRole.CITIZEN)
    jwt, _ = create_access_token(citizen.id, citizen.role.value)
    headers = {"Authorization": f"Bearer {jwt}"}
    before = sample(scrape(client).text, "raksha_incidents_open")
    for _ in range(2):
        assert (
            client.post(
                "/api/v1/incidents", json=incident_payload, headers=headers
            ).status_code
            == 201
        )

    body = scrape(client).text
    assert sample(body, "raksha_incidents_open") == before + 2
    assert sample(body, "raksha_incidents_unassigned_open") >= 2
    assert sample(body, "raksha_database_up") == 1.0


def test_pool_gauges_are_exposed(client: TestClient, scraping) -> None:
    body = scrape(client).text
    for name in (
        "raksha_db_pool_size",
        "raksha_db_pool_checked_out",
        "raksha_db_pool_overflow",
    ):
        assert name in body
    assert sample(body, "raksha_db_pool_size") > 0
