"""A host-supplied database URL must reach SQLAlchemy in the driver form we install.

Managed PostgreSQL hosts hand out ``postgresql://`` (some ``postgres://``) URLs.
SQLAlchemy reads a bare ``postgresql://`` as psycopg2, which this project does not
install - it ships psycopg 3 - so such a URL used to fail at engine creation with
``No module named 'psycopg2'``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.core.config import Settings, normalise_database_url

PSYCOPG = "postgresql+psycopg://"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgresql://u:p@db:5432/raksha", PSYCOPG + "u:p@db:5432/raksha"),
        ("postgres://u:p@db:5432/raksha", PSYCOPG + "u:p@db:5432/raksha"),
        ("POSTGRESQL://u:p@db/raksha", PSYCOPG + "u:p@db/raksha"),
        ("  postgresql://u:p@db/raksha\n", PSYCOPG + "u:p@db/raksha"),
    ],
)
def test_a_plain_postgres_url_is_rewritten_to_the_psycopg_driver(
    given: str, expected: str
) -> None:
    assert normalise_database_url(given) == expected


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@db/raksha",
        "postgresql+psycopg2://u:p@db/raksha",
        "postgresql+asyncpg://u:p@db/raksha",
    ],
)
def test_a_url_that_names_a_driver_is_left_alone(url: str) -> None:
    assert normalise_database_url(url) == url


def test_everything_after_the_scheme_is_preserved() -> None:
    url = "postgres://user:p%40ss%2Fw%3Ard@dpg-x.example.com:5432/db?sslmode=require&x=1"
    assert normalise_database_url(url) == (
        PSYCOPG + "user:p%40ss%2Fw%3Ard@dpg-x.example.com:5432/db?sslmode=require&x=1"
    )


def test_settings_apply_the_rewrite_to_database_url() -> None:
    settings = Settings(database_url="postgresql://u:p@db:5432/raksha")
    assert settings.sqlalchemy_database_uri == PSYCOPG + "u:p@db:5432/raksha"


@pytest.mark.parametrize("scheme", ["postgresql", "postgres"])
def test_a_host_url_builds_an_engine_on_the_installed_driver(scheme: str) -> None:
    """The regression itself: engine creation, not just string handling."""
    settings = Settings(database_url=f"{scheme}://u:p@db:5432/raksha")
    engine = create_engine(settings.sqlalchemy_database_uri)  # lazy: does not connect
    assert engine.dialect.driver == "psycopg"


def test_the_component_settings_still_build_a_psycopg_url() -> None:
    settings = Settings(
        database_url=None,
        postgres_user="u",
        postgres_password="p",
        postgres_host="db",
        postgres_port=5432,
        postgres_db="raksha",
    )
    assert settings.sqlalchemy_database_uri == PSYCOPG + "u:p@db:5432/raksha"
