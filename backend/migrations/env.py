"""Alembic environment.

The database URL comes from ``app.core.config`` so migrations use exactly the
same configuration source as the application, and no credential lives in
``alembic.ini``.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

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


def include_object(object_, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    """Skip PostGIS' own managed objects.

    ``spatial_ref_sys`` belongs to the extension, not to this application, and
    autogenerate must never propose dropping it.
    """
    return not (
        type_ == "table"
        and name in {"spatial_ref_sys", "geography_columns", "geometry_columns"}
    )


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
