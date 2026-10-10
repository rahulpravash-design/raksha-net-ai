"""Is the database schema the one this code expects? (Phase 18)

Starting a new version before its migration has run is the classic way a
deployment breaks, and the symptom is a wave of 500s from the first query that
touches a missing column. Readiness can notice it instead: an instance whose
schema is *behind* is not ready, so the orchestrator holds traffic back until
the migration has run.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[2]

CURRENT = "current"
BEHIND = "behind"
AHEAD = "ahead"
UNKNOWN = "unknown"


@lru_cache
def _script() -> ScriptDirectory | None:
    ini = BACKEND_ROOT / "alembic.ini"
    if not ini.is_file():
        return None
    config = Config(str(ini))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return ScriptDirectory.from_config(config)


def code_head() -> str | None:
    script = _script()
    if script is None:
        return None
    heads = script.get_heads()
    return heads[0] if len(heads) == 1 else None


def schema_state(session: Session) -> str:
    """``current``, ``behind``, ``ahead`` or ``unknown``.

    ``unknown`` is deliberate for a missing or empty version table (a database
    built by ``create_all`` in tests, or one downgraded to base): there is no
    recorded revision to compare, which is not the same as being behind.
    ``ahead`` means the database holds a revision this code has never heard of,
    as after rolling the application back past a migration.
    """
    script, head = _script(), code_head()
    if script is None or head is None:
        return UNKNOWN
    try:
        recorded = session.scalar(text("SELECT version_num FROM alembic_version"))
    except SQLAlchemyError:
        session.rollback()  # the table does not exist
        return UNKNOWN
    if recorded is None:
        return UNKNOWN
    if recorded == head:
        return CURRENT
    try:
        script.get_revision(recorded)
    except CommandError:
        return AHEAD
    return BEHIND
