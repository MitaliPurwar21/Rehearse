"""Database engine + session factory.

SQLite by default (a file, zero setup) — swap DATABASE_URL for Postgres later without
touching anything else.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from rehearse_core.config import get_settings
from services.api.models import Base


def normalize_url(url: str) -> str:
    # Some providers (Neon, Heroku) hand out the old `postgres://` scheme; SQLAlchemy
    # only accepts `postgresql://`.
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def make_engine(url: str) -> Engine:
    url = normalize_url(url)
    # check_same_thread is a SQLite quirk; harmless to skip for other databases.
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create tables if they don't exist."""
    Base.metadata.create_all(engine)
