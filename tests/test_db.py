"""Database URL handling — the postgres:// -> postgresql:// fix that lets Neon/Heroku
connection strings work with SQLAlchemy."""

from services.api.db import normalize_url


def test_postgres_scheme_is_upgraded() -> None:
    out = normalize_url("postgres://user:pw@host/db?sslmode=require")
    assert out == "postgresql://user:pw@host/db?sslmode=require"


def test_postgresql_scheme_unchanged() -> None:
    url = "postgresql://user:pw@host/db"
    assert normalize_url(url) == url


def test_sqlite_unchanged() -> None:
    assert normalize_url("sqlite:///./rehearse.db") == "sqlite:///./rehearse.db"
