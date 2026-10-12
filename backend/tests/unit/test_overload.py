"""Overload behaviour: bounded concurrency, and an honest 503 instead of a hang."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.core import metrics
from app.core.config import Settings
from app.core.errors import register_exception_handlers
from app.core.middleware import ConcurrencyLimitMiddleware


def build_app(limit: int, wait: float = 0.2) -> FastAPI:
    settings = Settings(max_concurrent_requests=limit, max_concurrent_wait_seconds=wait)
    app = FastAPI()
    app.add_middleware(ConcurrencyLimitMiddleware, settings=settings)
    register_exception_handlers(app)

    @app.get("/slow")
    async def slow() -> dict[str, str]:
        await asyncio.sleep(0.5)
        return {"ok": "yes"}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("handler failed")

    @app.get("/pool")
    async def pool() -> None:
        raise PoolTimeoutError("QueuePool limit of size 10 overflow 20 reached")

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


@pytest.mark.anyio
async def test_requests_over_the_limit_are_refused_with_retry_after() -> None:
    async with client(build_app(limit=2)) as c:
        responses = await asyncio.gather(*[c.get("/slow") for _ in range(4)])

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200, 200, 503, 503]
    busy = next(r for r in responses if r.status_code == 503)
    assert busy.headers["Retry-After"] == "1"
    assert busy.json()["error"]["code"] == "SERVICE_BUSY"


@pytest.mark.anyio
async def test_a_short_surge_is_queued_not_refused() -> None:
    """If a slot frees within the wait, the request is served, not shed."""
    async with client(build_app(limit=1, wait=2.0)) as c:
        responses = await asyncio.gather(*[c.get("/slow") for _ in range(2)])
    assert [r.status_code for r in responses] == [200, 200]


@pytest.mark.anyio
async def test_a_failing_request_releases_its_slot() -> None:
    """An exception must not leak a slot, or the API would seize up."""
    async with client(build_app(limit=1)) as c:
        for _ in range(3):
            assert (await c.get("/boom")).status_code == 500
        assert (await c.get("/slow")).status_code == 200


@pytest.mark.anyio
async def test_health_probes_bypass_the_limit() -> None:
    async with client(build_app(limit=1, wait=0.05)) as c:
        slow = asyncio.create_task(c.get("/slow"))
        await asyncio.sleep(0.05)
        assert (await c.get("/api/v1/health")).status_code == 200
        await slow


@pytest.mark.anyio
async def test_a_limit_of_zero_disables_the_cap() -> None:
    async with client(build_app(limit=0, wait=0.01)) as c:
        responses = await asyncio.gather(*[c.get("/slow") for _ in range(5)])
    assert all(r.status_code == 200 for r in responses)


@pytest.mark.anyio
async def test_pool_exhaustion_is_a_503_not_a_500() -> None:
    async with client(build_app(limit=5)) as c:
        response = await c.get("/pool")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_BUSY"
    assert response.headers["Retry-After"] == "2"


def counter(name: str) -> float:
    return metrics.REGISTRY.get_sample_value(name) or 0.0


@pytest.mark.anyio
async def test_overload_is_visible_in_the_metrics() -> None:
    """Queued and shed requests, and pool exhaustion, must show up as numbers:
    they are what would have revealed the Phase 17 deadlock early."""
    queued = counter("raksha_requests_queued_total")
    shed = counter("raksha_requests_shed_total")
    exhausted = counter("raksha_db_pool_exhausted_total")

    async with client(build_app(limit=1, wait=0.1)) as c:
        await asyncio.gather(*[c.get("/slow") for _ in range(3)])
        await c.get("/pool")

    assert counter("raksha_requests_queued_total") == queued + 2  # two had to wait
    assert counter("raksha_requests_shed_total") == shed + 2  # and neither got a slot
    assert counter("raksha_db_pool_exhausted_total") == exhausted + 1


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
