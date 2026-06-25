"""Caching in run_eval — judge once, reuse after. No network: a FakeProvider
stands in for the model and the cache dir is redirected to a temp folder."""

from pathlib import Path

import pytest

import eval.run_eval as run_eval
from eval.golden import GoldenSession
from eval.runner import JudgeRunner
from eval.schemas import CompetencyEvaluation, DimensionScore, SessionEvaluation
from rehearse_core.llm.fake import FakeProvider


def _canned() -> SessionEvaluation:
    scores = {"relevance": 4, "depth": 2, "evidence": 2, "communication": 4}
    dims = [
        DimensionScore(dimension=d, rationale="r", score=s, evidence_quotes=["q"])  # type: ignore[arg-type]
        for d, s in scores.items()
    ]
    return SessionEvaluation(
        competency_evaluations=[
            CompetencyEvaluation(
                competency="RAG systems",
                dimension_scores=dims,
                competency_score=3.0,
                summary_feedback="ok",
            )
        ],
        overall_feedback="fine",
    )


def _session() -> GoldenSession:
    return GoldenSession(
        session_id="t1",
        split="validation",
        job_description="ML engineer building RAG.",
        competencies=["RAG systems"],
        turns=[{"speaker": "interviewer", "text": "Tell me about RAG."}],
    )


def test_judge_or_cache_misses_then_hits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_eval, "_CACHE_DIR", tmp_path / "judgements")
    runner = JudgeRunner(FakeProvider(_canned()))

    first, cached_first = run_eval._judge_or_cache(runner, _session())
    assert cached_first is False  # nothing on disk yet

    second, cached_second = run_eval._judge_or_cache(runner, _session())
    assert cached_second is True  # served from the file written on the first call
    assert second.competency_evaluations[0].competency == "RAG systems"


def test_cache_key_survives_slashes_in_model_id() -> None:
    path = run_eval._cache_path("t1", "meta-llama/llama-4", "abcdef0123456789")
    assert "/" not in path.name
