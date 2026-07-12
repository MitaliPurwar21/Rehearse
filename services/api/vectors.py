"""A SQLAlchemy column type for embeddings.

On Postgres it's a real pgvector column (so the cosine-distance operator and an index work in
the database); on SQLite it falls back to JSON, so local dev and the tests need no extension.
Same Python value (a list of floats) either way.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Dialect, TypeDecorator
from sqlalchemy.types import TypeEngine


class Embedding(TypeDecorator[list[float]]):
    impl = JSON
    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim
        super().__init__()

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_result_value(self, value: Any, dialect: Dialect) -> list[float] | None:
        if value is None:
            return None
        return [float(x) for x in value]
