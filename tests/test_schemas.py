"""Tests for the schema validators — these are what stop the judge handing back
ungrounded or inconsistent scores, so they're worth checking directly.
"""

import pytest
from pydantic import ValidationError

from eval.schemas import CompetencyEvaluation, DimensionScore


def _dim(dimension: str, score: int, quotes: list[str] | None = None) -> DimensionScore:
    return DimensionScore(
        dimension=dimension,  # type: ignore[arg-type]
        rationale="because",
        score=score,
        evidence_quotes=quotes or [],
    )


def _all_dims(scores: dict[str, int], quotes: list[str]) -> list[DimensionScore]:
    return [_dim(d, s, quotes if s != 3 else []) for d, s in scores.items()]


def test_high_score_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        _dim("depth", 5, quotes=[])


def test_score_two_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        _dim("depth", 2, quotes=[])


def test_neutral_score_allows_no_evidence() -> None:
    assert _dim("depth", 3, quotes=[]).score == 3


def test_score_one_allows_no_evidence() -> None:
    # A 1 means off-topic/absent — there may be nothing to quote.
    assert _dim("relevance", 1, quotes=[]).score == 1


def test_competency_requires_all_four_dimensions() -> None:
    with pytest.raises(ValidationError):
        CompetencyEvaluation(
            competency="RAG",
            dimension_scores=[_dim("depth", 3), _dim("relevance", 3)],
            competency_score=3.0,
            summary_feedback="x",
        )


def test_competency_score_must_match_dimension_mean() -> None:
    scores = {"relevance": 2, "depth": 2, "evidence": 2, "communication": 2}
    with pytest.raises(ValidationError):
        CompetencyEvaluation(
            competency="RAG",
            dimension_scores=_all_dims(scores, ["q"]),
            competency_score=5.0,  # mean is 2.0 — inconsistent
            summary_feedback="x",
        )


def test_valid_competency_passes() -> None:
    scores = {"relevance": 4, "depth": 2, "evidence": 2, "communication": 4}
    comp = CompetencyEvaluation(
        competency="RAG",
        dimension_scores=_all_dims(scores, ["I turned up top_k to 50"]),
        competency_score=3.0,  # mean of [4,2,2,4]
        summary_feedback="solid framing, weak measurement",
    )
    assert comp.competency_score == 3.0
