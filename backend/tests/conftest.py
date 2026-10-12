"""Shared test fixtures.

Integration tests run against a real PostgreSQL + PostGIS instance. SQLite is
deliberately not substituted: it has no ``geography`` type, no ``ST_DWithin``
and different enum and constraint semantics, so a suite that passed on it would
say nothing about the queries this system actually runs
(``docs/TESTING.md`` section 2).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("RAKSHA_ENVIRONMENT", "test")
os.environ.setdefault(
    "RAKSHA_SECRET_KEY", "test-secret-key-not-used-anywhere-else-0123456789"
)
os.environ.setdefault("RAKSHA_RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("RAKSHA_BCRYPT_ROUNDS", "4")  # keep the suite fast
os.environ.setdefault("RAKSHA_LOG_LEVEL", "WARNING")

import app.models  # noqa: F401  - registers every mapper
from app.core.config import get_settings
from app.core.rate_limit import RateLimiter, set_rate_limiter
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.enums import UserRole
from app.models.user import User


def _test_database_url() -> str:
    settings = get_settings()
    if settings.test_database_url:
        return settings.test_database_url.get_secret_value()
    base = settings.sqlalchemy_database_uri
    return base if base.endswith("_test") else f"{base}_test"


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    engine = create_engine(_test_database_url(), future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment problem, not a test failure
        pytest.skip(f"Test database is unavailable: {exc}")

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """A session wrapped in a transaction that is rolled back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def fresh_rate_limiter() -> Iterator[None]:
    """Give each test its own counters so limits never leak between tests."""
    set_rate_limiter(RateLimiter())
    yield
    set_rate_limiter(RateLimiter())


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """An API client bound to the test transaction."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db_session: Session):
    """Build a persisted user with a known password."""
    from app.core.security import hash_password

    default_password = "correct-horse-battery-staple"

    def _make(
        role: UserRole = UserRole.CITIZEN,
        *,
        email: str | None = None,
        password: str = default_password,
        is_active: bool = True,
        full_name: str = "Test Person",
    ) -> User:
        user = User(
            email=email or f"{role.value.lower()}-{uuid.uuid4().hex[:8]}@example.org",
            full_name=full_name,
            hashed_password=hash_password(password),
            role=role,
            is_active=is_active,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    _make.password = default_password  # type: ignore[attr-defined]
    return _make


@pytest.fixture
def authed_client(client: TestClient):
    """Return a factory that authenticates the client as a given user."""

    def _as(user: User) -> TestClient:
        from app.core.security import create_access_token

        token, _ = create_access_token(user.id, user.role.value)
        client.headers["Authorization"] = f"Bearer {token}"
        return client

    return _as


@pytest.fixture
def as_role(client: TestClient, make_user, authed_client):
    """Create a user of the given role and authenticate as them."""

    def _as(role: UserRole) -> tuple[TestClient, User]:
        user = make_user(role)
        return authed_client(user), user

    return _as


@pytest.fixture
def incident_payload() -> dict[str, object]:
    """A valid report inside the default operating bounding box (Chennai)."""
    return {
        "category": "FLOOD",
        "description": "Five people are trapped inside a house and water is rising fast.",
        "latitude": 13.0827,
        "longitude": 80.2707,
        "address_text": "2nd Street, Kotturpuram",
        "people_affected": 5,
        "people_trapped": True,
        "medical_required": True,
        "immediate_danger": True,
    }


@pytest.fixture(autouse=True)
def _isolate_media_storage(tmp_path, monkeypatch):
    """Point uploads at a per-test directory."""
    settings = get_settings()
    monkeypatch.setattr(settings, "media_storage_path", tmp_path / "media")
    yield


def unused(_: object) -> None:  # pragma: no cover - silences unused-import linters
    return None


@pytest.fixture(autouse=True)
def _stay_clear_of_the_rate_limit_window_edge(request: pytest.FixtureRequest) -> None:
    """Rate limiting is fixed-window (docs/SECURITY.md): counters reset at each
    minute boundary, so a test that counts requests across the boundary sees the
    count restart and fails about once in a dozen runs. Rate-limit tests wait out
    the last few seconds of a window instead of racing it."""
    if "rate_limit" not in request.node.nodeid:
        return
    import time

    remaining = 60 - (time.time() % 60)
    if remaining < 6:
        time.sleep(remaining + 0.2)
