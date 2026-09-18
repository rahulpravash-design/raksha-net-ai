"""Engine, session factory and the FastAPI database dependency."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.sqlalchemy_database_uri,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,  # survive a database restart without a failed request
        echo=settings.db_echo,
        future=True,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(), autocommit=False, autoflush=False, expire_on_commit=False
    )


def get_db() -> Generator[Session, None, None]:
    """Yield a session that is rolled back on any unhandled exception.

    Services commit explicitly; anything that escapes is treated as a failed
    unit of work.
    """
    session = get_session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
