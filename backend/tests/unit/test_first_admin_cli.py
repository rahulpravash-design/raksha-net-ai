"""The first-administrator command's handling of input, failure and secrets.

No database: the service is replaced where a test needs it, and a session opener that
fails the test stands in wherever the database must not be reached.
"""

from __future__ import annotations

import getpass
import io
import sys
import uuid
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from app.cli import create_first_admin as cli
from app.core.config import Environment, get_settings
from app.core.errors import AdminAlreadyExistsError, EmailAlreadyRegisteredError
from app.schemas.user import FirstAdminCreate
from app.services.bootstrap_service import BootstrapService

ARGS = ["--email", "founder@example.org", "--name", "Founding Administrator"]
SECRET = "VerySecret-Passphrase-1"


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def database_must_not_be_touched():
    raise AssertionError("the database must not be touched")


def run(argv, *, stdin: str | None = None, opener=database_must_not_be_touched):
    if stdin is not None:
        sys.stdin = io.StringIO(stdin)
    return cli.main(argv, open_session=opener)


@pytest.fixture(autouse=True)
def restore_stdin():
    original = sys.stdin
    yield
    sys.stdin = original


@pytest.fixture
def captured(monkeypatch):
    """Replace the service's create method; collect what it was given."""
    seen: list[FirstAdminCreate] = []

    def fake(self, payload: FirstAdminCreate):
        seen.append(payload)
        return SimpleNamespace(email=payload.email, id=uuid.uuid4())

    monkeypatch.setattr(BootstrapService, "create_first_admin", fake)
    return seen


def no_database():
    return nullcontext(None)


# --- the password -------------------------------------------------------------
def test_stdin_password_loses_only_its_line_ending(captured, capsys) -> None:
    code = run(
        [*ARGS, "--password-stdin"],
        stdin="  spaced pass phrase  \r\n",
        opener=no_database,
    )

    assert code == cli.EXIT_CREATED
    assert captured[0].password == "  spaced pass phrase  "
    out = capsys.readouterr()
    assert "spaced pass phrase" not in out.out + out.err


def test_the_prompt_asks_twice_and_the_password_never_reaches_the_output(
    captured, capsys, monkeypatch
) -> None:
    sys.stdin = Terminal()
    answers = iter([SECRET, SECRET])
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(answers))

    assert cli.main(ARGS, open_session=no_database) == cli.EXIT_CREATED
    out = capsys.readouterr()
    assert captured[0].password == SECRET
    assert SECRET not in out.out + out.err


def test_two_different_answers_are_refused_without_touching_the_database(
    capsys, monkeypatch
) -> None:
    sys.stdin = Terminal()
    answers = iter([SECRET, SECRET + "x"])
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(answers))

    assert cli.main(ARGS, open_session=database_must_not_be_touched) == cli.EXIT_INVALID
    err = capsys.readouterr().err
    assert "differ" in err
    assert SECRET not in err


def test_without_a_terminal_or_the_flag_it_refuses_to_guess(capsys) -> None:
    assert run(ARGS, stdin=SECRET + "\n") == cli.EXIT_INVALID
    err = capsys.readouterr().err
    assert "--password-stdin" in err
    assert SECRET not in err


def test_an_empty_password_is_refused(capsys) -> None:
    assert run([*ARGS, "--password-stdin"], stdin="\n") == cli.EXIT_INVALID
    assert "empty" in capsys.readouterr().err


def test_a_weak_password_is_refused_before_the_database_is_used(capsys) -> None:
    # The service validates the password first; a session of None would fail loudly
    # if anything reached the database.
    assert (
        run([*ARGS, "--password-stdin"], stdin="short\n", opener=no_database)
        == cli.EXIT_INVALID
    )
    assert "at least" in capsys.readouterr().err


def test_a_validation_error_does_not_repeat_the_password(capsys) -> None:
    code = run(
        ["--email", "not-an-email", "--name", "X Y", "--password-stdin"],
        stdin=SECRET + "\n",
    )

    assert code == cli.EXIT_INVALID
    err = capsys.readouterr().err
    assert "email" in err
    assert "VerySecret" not in err


# --- configuration and failures ----------------------------------------------
def test_an_unsafe_production_configuration_is_refused_before_anything_is_read(
    monkeypatch, capsys
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", Environment.PRODUCTION)
    monkeypatch.setattr(settings, "debug", True)
    stdin = io.StringIO(SECRET + "\n")
    sys.stdin = stdin

    code = cli.main(
        [*ARGS, "--password-stdin"], open_session=database_must_not_be_touched
    )

    assert code == cli.EXIT_INVALID
    assert "Refusing to run" in capsys.readouterr().err
    assert stdin.tell() == 0  # the password was never read


def test_an_existing_administrator_is_a_refusal(monkeypatch, capsys) -> None:
    def refuse(self, payload):
        raise AdminAlreadyExistsError()

    monkeypatch.setattr(BootstrapService, "create_first_admin", refuse)

    assert (
        run([*ARGS, "--password-stdin"], stdin=SECRET + "\n", opener=no_database)
        == cli.EXIT_REFUSED
    )
    err = capsys.readouterr().err
    assert "already exists" in err
    assert "control centre" in err


def test_a_taken_email_is_a_refusal(monkeypatch, capsys) -> None:
    def refuse(self, payload):
        raise EmailAlreadyRegisteredError()

    monkeypatch.setattr(BootstrapService, "create_first_admin", refuse)

    assert (
        run([*ARGS, "--password-stdin"], stdin=SECRET + "\n", opener=no_database)
        == cli.EXIT_REFUSED
    )
    assert "already exists" in capsys.readouterr().err


def test_a_database_failure_is_reported_without_its_details(monkeypatch, capsys) -> None:
    def fail(self, payload):
        raise OperationalError(
            "SELECT 1", {}, Exception("password authentication failed for user raksha")
        )

    monkeypatch.setattr(BootstrapService, "create_first_admin", fail)

    assert (
        run([*ARGS, "--password-stdin"], stdin=SECRET + "\n", opener=no_database)
        == cli.EXIT_UNAVAILABLE
    )
    err = capsys.readouterr().err
    assert "OperationalError" in err
    assert "alembic upgrade head" in err
    assert "password authentication" not in err
