"""What a browser sees when the backend has a bug.

Starlette answers an uncaught exception from its outermost layer, outside CORS. The
response then has no ``Access-Control-Allow-Origin``, so a browser hides its status and
reports a bare network failure — a backend bug reads to the visitor as "could not reach
the server". These tests pin the fix: the 500 is produced inside the other middleware.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

SECRET_DETAIL = "connection string was postgresql://admin:hunter2@10.0.0.5/raksha"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()

    @app.get("/test-only/boom")
    def boom() -> None:
        raise RuntimeError(SECRET_DETAIL)

    @app.get("/test-only/forbidden")
    def forbidden() -> None:
        raise HTTPException(status_code=403, detail="no")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_an_uncaught_exception_is_a_500_envelope(client: TestClient) -> None:
    response = client.get("/test-only/boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


def test_the_500_carries_cors_headers_so_the_browser_can_read_it(
    client: TestClient,
) -> None:
    origin = get_settings().cors_origins[0]

    response = client.get("/test-only/boom", headers={"Origin": origin})

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == origin


def test_the_500_leaks_none_of_the_exception(client: TestClient) -> None:
    body = client.get("/test-only/boom").text

    assert "hunter2" not in body
    assert "RuntimeError" not in body
    assert "Traceback" not in body


def test_the_500_still_passes_through_the_outer_layers(client: TestClient) -> None:
    """The point of being innermost: request id and security headers still apply."""
    response = client.get("/test-only/boom", headers={"X-Request-ID": "abc123"})

    assert response.headers["x-request-id"] == "abc123"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_the_detail_is_logged_not_returned(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("ERROR"):
        client.get("/test-only/boom")

    assert any(record.getMessage() == "unhandled_exception" for record in caplog.records)


def test_expected_errors_are_left_alone(client: TestClient) -> None:
    """Only the unexpected is caught: an HTTPException keeps its own status."""
    assert client.get("/test-only/forbidden").status_code == 403
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/no-such-route").status_code == 404
