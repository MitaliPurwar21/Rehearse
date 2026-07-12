"""Offline tests for semantic resume retrieval. No model load, no network.

A fake keyword-count embedder stands in for the real one so ranking is deterministic and the
tests run on SQLite (the JSON fallback for the embedding column).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from retrieval.store import add_resume, cosine, search
from services.api.models import Base

_KEYWORDS = ["python", "java", "react"]


def _fake_embedder(texts: list[str]) -> list[list[float]]:
    # A crude but deterministic "embedding": how often each keyword appears.
    return [[float(t.lower().count(kw)) for kw in _KEYWORDS] for t in texts]


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_cosine() -> None:
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0  # guarded against divide-by-zero


def test_search_ranks_by_similarity(db: Session) -> None:
    add_resume(db, "Py Dev", "python python python", _fake_embedder)
    add_resume(db, "Java Dev", "java java", _fake_embedder)
    add_resume(db, "FE Dev", "react react react", _fake_embedder)

    results = search(db, "senior python engineer", 2, _fake_embedder)
    assert len(results) == 2
    assert results[0][0].name == "Py Dev"  # closest to a python JD
    assert results[0][1] > results[1][1]  # sorted by similarity descending


def test_search_respects_k(db: Session) -> None:
    for i in range(4):
        add_resume(db, f"c{i}", "python", _fake_embedder)
    assert len(search(db, "python", 2, _fake_embedder)) == 2
