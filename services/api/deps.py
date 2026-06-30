"""FastAPI dependencies — what routes ask for.

Both are overridden in tests: the DB points at a throwaway database, and the provider
becomes a FakeProvider, so the API is fully testable without a real database or any
LLM calls.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from rehearse_core.config import get_settings
from rehearse_core.llm.base import LLMProvider
from rehearse_core.llm.factory import build_provider
from services.api.db import SessionLocal


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_provider() -> LLMProvider:
    return build_provider(get_settings())
