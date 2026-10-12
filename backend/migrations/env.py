"""Alembic environment.

The database URL comes from ``app.core.config`` so migrations use exactly the
same configuration source as the application, and no credential lives in
``alembic.ini``.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool, text

# Importing the models package registers every mapper on ``Base.metadata``,
# which autogenerate compares against.
import app.models  # noqa: F401
from app.core.config import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_database_url = (
    os.getenv("ALEMBIC_DATABASE_URL") or get_settings().sqlalchemy_database_uri
)
config.set_main_option("sqlalchemy.url", _database_url.replace("%", "%%"))


#: PostGIS' own tables and views. They belong to the extension, not to this
#: application, and autogenerate must never propose dropping them. Offline mode has
#: no database to ask, so these are named; online mode also asks the catalog.
_POSTGIS_RELATIONS = frozenset(
    {"spatial_ref_sys", "geography_columns", "geometry_columns"}
)

_EXTENSION_RELATIONS_SQL = text("""
    SELECT c.relname
    FROM pg_depend d
    JOIN pg_class c ON c.oid = d.objid
    WHERE d.classid = 'pg_class'::regclass AND d.deptype = 'e'
    """)


def _extension_relations(connection: Connection) -> frozenset[str]:
    """Every table and view that an installed PostgreSQL extension owns.

    The ``postgis/postgis`` image (CI and docker-compose) also installs the
    topology and TIGER geocoder extensions and puts their schemas on the search
    path, so reflection sees their tables beside this application's. Without this
    filter ``alembic check`` reports each of them as a table the models dropped.
    """
    return _POSTGIS_RELATIONS | frozenset(
        connection.execute(_EXTENSION_RELATIONS_SQL).scalars()
    )


def _object_filter(foreign: frozenset[str]):  # type: ignore[no-untyped-def]
    """Skip database objects that belong to an extension rather than to the models.

    Only objects found in the database and absent from the models are skipped, so
    a model whose table is missing is still reported, and so is a table left
    behind by a model that was removed.
    """

    def include_object(object_, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
        if not reflected or compare_to is not None:
            return True
        if type_ == "table":
            return name not in foreign
        table = getattr(object_, "table", None)
        return table is None or table.name not in foreign

    return include_object


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=_object_filter(_POSTGIS_RELATIONS),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # Read the catalog on a connection of its own. A query on the migration
    # connection would begin a transaction that alembic then joins instead of
    # owning, and the migrations would run but never be committed.
    with connectable.connect() as probe:
        foreign = _extension_relations(probe)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=_object_filter(foreign),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
