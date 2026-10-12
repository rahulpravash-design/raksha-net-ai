"""Settings must not print their credentials.

``repr(settings)``, ``str(settings)``, ``model_dump()`` and ``model_dump_json()`` are what
end up in a log line, a crash report or a debugging session. A connection URL carries the
database password, so it must be masked like every other secret - including the assembled
``sqlalchemy_database_uri``, which used to be a pydantic computed field and so was printed
in the clear.
"""

from __future__ import annotations

import re
import types
import typing

import pytest
from pydantic import SecretStr

from app.core.config import Settings

# One recognisable value per credential; none may appear in any printed form.
SENTINELS = {
    "database_url": "dbpw-A1b2C3",
    "test_database_url": "testdbpw-D4e5F6",
    "redis_url": "redispw-G7h8I9",
    "postgres_password": "pgcomponentpw-J1k2L3",
    "secret_key": "signingkey-M4n5O6-xxxxxxxxxxxxxxxxxxxxxxxx",
    "encryption_key": "fernetkey-P7q8R9",
    "smtp_password": "smtppw-S1t2U3",
    "metrics_token": "metricstoken-V4w5X6",
    "ai_api_key": "aikey-Y7z8A9",
}


def configured() -> Settings:
    return Settings(
        database_url=f"postgres://u:{SENTINELS['database_url']}@h:5432/d",
        test_database_url=f"postgresql+psycopg://u:{SENTINELS['test_database_url']}@h/d_test",
        redis_url=f"redis://:{SENTINELS['redis_url']}@h:6379/0",
        postgres_password=SENTINELS["postgres_password"],
        secret_key=SENTINELS["secret_key"],
        encryption_key=SENTINELS["encryption_key"],
        smtp_password=SENTINELS["smtp_password"],
        metrics_token=SENTINELS["metrics_token"],
        ai_api_key=SENTINELS["ai_api_key"],
    )


def printed_forms(settings: Settings) -> dict[str, str]:
    return {
        "repr": repr(settings),
        "str": str(settings),
        "model_dump": str(settings.model_dump()),
        "model_dump_json": settings.model_dump_json(),
    }


@pytest.mark.parametrize("form", ["repr", "str", "model_dump", "model_dump_json"])
def test_no_credential_appears_in_any_printed_form(form: str) -> None:
    text = printed_forms(configured())[form]
    leaked = [name for name, value in SENTINELS.items() if value in text]
    assert not leaked, f"{form} exposes {leaked}"


def test_the_assembled_url_is_not_printed_when_it_is_built_from_the_components() -> None:
    """The default setup (no database_url): the password sits in postgres_password and
    is copied into sqlalchemy_database_uri, which must not be dumped."""
    settings = Settings(
        database_url=None, postgres_password=SENTINELS["postgres_password"]
    )

    assert SENTINELS["postgres_password"] in settings.sqlalchemy_database_uri
    assert "sqlalchemy_database_uri" not in settings.model_dump()
    for form, text in printed_forms(settings).items():
        assert SENTINELS["postgres_password"] not in text, form


def test_the_code_that_needs_the_values_can_still_read_them() -> None:
    settings = configured()

    assert settings.sqlalchemy_database_uri == (
        f"postgresql+psycopg://u:{SENTINELS['database_url']}@h:5432/d"
    )
    assert settings.redis_url.get_secret_value() == (
        f"redis://:{SENTINELS['redis_url']}@h:6379/0"
    )
    assert settings.test_database_url is not None
    assert SENTINELS["test_database_url"] in settings.test_database_url.get_secret_value()


# --- a guard against the next one -------------------------------------------------
CREDENTIAL_NAME = re.compile(
    r"password|secret|token|api_key|encryption_key|database_url|redis_url"
)


def _types_in(annotation: object) -> set[object]:
    """The member types of ``X | None`` / ``Optional[X]``, or the type itself."""
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        return {
            member for arg in typing.get_args(annotation) for member in _types_in(arg)
        }
    return {annotation}


def test_every_setting_that_can_carry_a_credential_is_a_secretstr() -> None:
    """A new ``something_password: str`` or ``x_database_url: str`` fails here, instead of
    quietly showing up in the next log line that prints settings."""
    offenders = []
    for name, field in Settings.model_fields.items():
        members = _types_in(field.annotation)
        if CREDENTIAL_NAME.search(name) and str in members and SecretStr not in members:
            offenders.append(name)

    assert not offenders, f"plain-string settings that look like credentials: {offenders}"
