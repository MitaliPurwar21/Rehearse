"""Semantic resume retrieval over a pool, backed by pgvector on Postgres.

Each resume is stored with its embedding. search() ranks the pool against a job description:
on Postgres it uses pgvector's cosine-distance operator so the database does the work (and an
index can back it); on SQLite it does the same ranking with an exact cosine scan in Python.
The pgvector path is what runs in production; the Python path keeps local dev and tests simple.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from services.api.models import ResumeDoc

Embedder = Callable[[list[str]], list[list[float]]]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def add_resume(db: Session, name: str, resume_text: str, embedder: Embedder) -> ResumeDoc:
    doc = ResumeDoc(name=name, resume_text=resume_text, embedding=embedder([resume_text])[0])
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def search(
    db: Session, jd_text: str, k: int, embedder: Embedder
) -> list[tuple[ResumeDoc, float]]:
    qvec = embedder([jd_text])[0]
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        literal = "[" + ",".join(str(x) for x in qvec) + "]"
        rows = db.execute(
            text(
                "SELECT id, 1 - (embedding <=> :q) AS sim FROM resume_docs "
                "ORDER BY embedding <=> :q LIMIT :k"
            ),
            {"q": literal, "k": k},
        ).all()
        out: list[tuple[ResumeDoc, float]] = []
        for row_id, sim in rows:
            doc = db.get(ResumeDoc, row_id)
            if doc is not None:
                out.append((doc, float(sim)))
        return out

    scored = [(d, cosine(qvec, d.embedding)) for d in db.scalars(select(ResumeDoc))]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:k]
