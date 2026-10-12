"""``scripts/render_start.sh``, run for real with stand-ins for alembic, python and uvicorn.

Each stand-in appends one line to a log, so the tests see the order of the steps, what
each received on its command line and standard input, and what was left in the
environment of the API process.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "render_start.sh"
SH = shutil.which("sh") or "/bin/sh"
PASSWORD = "Correct-Horse-Battery-9"

STAND_IN = """#!/bin/sh
name=$(basename "$0")
stdin=""
if [ "$name" = python ]; then stdin=$(cat); fi
printf '%s|args=%s|stdin=%s|pw_env=%s\\n' "$name" "$*" "$stdin" \
    "${FIRST_ADMIN_PASSWORD:-}" >> "$STAND_IN_LOG"
case "$name" in
    alembic) exit "${ALEMBIC_EXIT:-0}" ;;
    python) exit "${PYTHON_EXIT:-0}" ;;
esac
exit 0
"""


@pytest.fixture
def bin_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "bin"
    directory.mkdir()
    for name in ("alembic", "python", "uvicorn"):
        tool = directory / name
        tool.write_text(STAND_IN)
        tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    return directory


def run(bin_dir: Path, **env: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    log = bin_dir.parent / "calls.log"
    environment = {
        "PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "STAND_IN_LOG": str(log),
        **env,
    }
    result = subprocess.run(  # noqa: S603 - the repository's own script, fixed path
        [SH, str(SCRIPT)],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    calls = log.read_text().splitlines() if log.exists() else []
    return result, calls


def test_migrates_then_serves_on_the_assigned_port(bin_dir: Path) -> None:
    result, calls = run(bin_dir, PORT="10000")

    assert result.returncode == 0
    assert [call.split("|")[0] for call in calls] == ["alembic", "uvicorn"]
    assert "args=upgrade head" in calls[0]
    assert "--port 10000" in calls[1]
    assert "app.main:app" in calls[1]


def test_serves_on_8000_without_a_port(bin_dir: Path) -> None:
    _, calls = run(bin_dir)
    assert "--port 8000" in calls[-1]


def test_creates_the_first_admin_with_the_password_on_stdin_only(bin_dir: Path) -> None:
    result, calls = run(
        bin_dir,
        FIRST_ADMIN_EMAIL="founder@example.org",
        FIRST_ADMIN_NAME="Founding Administrator",
        FIRST_ADMIN_PASSWORD=PASSWORD,
    )

    assert result.returncode == 0
    assert [call.split("|")[0] for call in calls] == ["alembic", "python", "uvicorn"]
    bootstrap = calls[1]
    assert "--email founder@example.org" in bootstrap
    assert "--password-stdin --skip-if-admin-exists" in bootstrap
    assert f"stdin={PASSWORD}|" in bootstrap
    args = bootstrap.split("|")[1]
    assert PASSWORD not in args  # never on the command line
    assert calls[2].endswith("pw_env=")  # gone before the API starts
    assert PASSWORD not in result.stdout + result.stderr


def test_without_both_variables_no_administrator_is_attempted(bin_dir: Path) -> None:
    _, only_email = run(bin_dir, FIRST_ADMIN_EMAIL="founder@example.org")
    assert [call.split("|")[0] for call in only_email] == ["alembic", "uvicorn"]


def test_a_failed_bootstrap_is_reported_but_the_api_still_starts(bin_dir: Path) -> None:
    result, calls = run(
        bin_dir,
        FIRST_ADMIN_EMAIL="founder@example.org",
        FIRST_ADMIN_PASSWORD="short",
        PYTHON_EXIT="2",
    )

    assert result.returncode == 0
    assert calls[-1].startswith("uvicorn|")
    assert "NOT created (exit 2)" in result.stderr


def test_a_failed_migration_stops_the_start(bin_dir: Path) -> None:
    """Serving against a schema the code does not match is worse than not serving."""
    result, calls = run(bin_dir, ALEMBIC_EXIT="1")

    assert result.returncode != 0
    assert [call.split("|")[0] for call in calls] == ["alembic"]
