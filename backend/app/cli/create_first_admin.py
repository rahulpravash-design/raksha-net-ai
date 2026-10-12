"""Create the first super administrator of a deployment.

A new deployment has no administrator, and an administrator is the only thing that can
create one over the API, so this command is the way in. It is run by someone with a
shell on the deployment (a Render shell, ``docker compose exec``, a one-off job)::

    python -m app.cli.create_first_admin --email you@example.org --name "Your Name"

The password is typed at a hidden prompt. For scripted use, ``--password-stdin`` reads
it from standard input. It is never accepted as an argument, which would end up in
process listings and shell history. (A host without a shell, such as Render's free tier,
can feed it from a secret through ``backend/scripts/render_start.sh``; see
``docs/DEPLOYMENT.md`` 13.7.)

``--skip-if-admin-exists`` makes an existing administrator "nothing to do" (exit 0)
instead of a refusal, so a start-up script can run the command on every boot.

It creates one ``SUPER_ADMIN`` and refuses to run again once any administrator exists.
The account must choose a new password and, where policy requires, enrol two-factor
authentication at its first sign-in. See ``docs/DEPLOYMENT.md`` section 13.

Exit status: 0 created (or, with ``--skip-if-admin-exists``, an administrator already
existed); 2 bad input or an unsafe configuration; 3 refused because an administrator (or
the email address) already exists; 4 the database could not be used.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import app.models  # noqa: F401  - registers every mapper
from app.core.config import get_settings
from app.core.errors import (
    AdminAlreadyExistsError,
    AppError,
    EmailAlreadyRegisteredError,
)
from app.core.logging import configure_logging
from app.db.session import get_session_factory
from app.schemas.user import FirstAdminCreate
from app.services.bootstrap_service import BootstrapService

EXIT_CREATED = 0
EXIT_INVALID = 2
EXIT_REFUSED = 3
EXIT_UNAVAILABLE = 4

SessionOpener = Callable[[], AbstractContextManager[Session]]


class _InputError(Exception):
    """The command could not obtain usable input. The message is safe to print."""


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        # Only the line ending is removed: spaces may be part of a passphrase.
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        if not sys.stdin.isatty():
            raise _InputError(
                "Standard input is not a terminal. Run this in an interactive shell, "
                "or pass --password-stdin and pipe the password in."
            )
        password = getpass.getpass("Password: ")
        if getpass.getpass("Repeat password: ") != password:
            raise _InputError("The two passwords differ.")
    if not password:
        raise _InputError("The password is empty.")
    return password


def _describe(error: PydanticValidationError) -> str:
    """Field and message only. A raw validation error repeats the rejected input, which
    here would be the password."""
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
        for item in error.errors()
    )


def _fail(message: str) -> None:
    print(message, file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.create_first_admin",
        description="Create the first super administrator. Refuses if any "
        "administrator already exists.",
    )
    parser.add_argument("--email", required=True, help="Sign-in address of the account.")
    parser.add_argument("--name", required=True, help="The person's full name.")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the password from standard input instead of prompting.",
    )
    parser.add_argument(
        "--skip-if-admin-exists",
        action="store_true",
        help="Exit 0 without changes if an administrator already exists.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None, *, open_session: SessionOpener | None = None
) -> int:
    args = _parser().parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    try:
        # Do not create a privileged account in a deployment that would refuse to start.
        settings.assert_safe_for_environment()
    except RuntimeError as exc:
        _fail(f"Refusing to run: {exc}")
        return EXIT_INVALID

    try:
        password = _read_password(args.password_stdin)
    except _InputError as exc:
        _fail(str(exc))
        return EXIT_INVALID

    try:
        payload = FirstAdminCreate(
            email=args.email, full_name=args.name, password=password
        )
    except PydanticValidationError as exc:
        _fail(f"Invalid input: {_describe(exc)}")
        return EXIT_INVALID

    opener = open_session or get_session_factory()
    try:
        with opener() as session:
            user = BootstrapService(session, settings).create_first_admin(payload)
            email, user_id = user.email, user.id
    except (AdminAlreadyExistsError, EmailAlreadyRegisteredError) as exc:
        if isinstance(exc, AdminAlreadyExistsError) and args.skip_if_admin_exists:
            print("An administrator already exists; nothing to do.")
            return EXIT_CREATED
        _fail(f"Refused: {exc.message}")
        if isinstance(exc, AdminAlreadyExistsError):
            _fail(
                "Further administrators are created by an existing administrator in "
                "the control centre."
            )
        return EXIT_REFUSED
    except AppError as exc:  # a weak password, chiefly
        _fail(f"Invalid input: {exc.message}")
        return EXIT_INVALID
    except SQLAlchemyError as exc:
        _fail(
            f"The database could not be used ({type(exc).__name__}). Check the database "
            "settings, and that the migrations have run (alembic upgrade head)."
        )
        return EXIT_UNAVAILABLE

    print(f"Created super administrator {email} (id {user_id}).")
    print(
        "Sign in to the control centre with the password you just set. You will be asked "
        "to choose a new one and, where required, to enrol two-factor authentication "
        "before anything else; keep the recovery codes shown then."
    )
    return EXIT_CREATED


if __name__ == "__main__":
    raise SystemExit(main())
