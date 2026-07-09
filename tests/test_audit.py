"""Judge-audit helpers and pipeline, all offline. A FakeProvider stands in for the
model and the caches are redirected to a temp folder, so nothing here hits the
network. The math helpers are checked against values worked out by hand."""

import math
from pathlib import Path

import pytest

import eval.audit as audit
import eval.run_eval as run_eval
from eval.audit import (
    _dim_scores,
    _shift,
    _stability,
    pad_answer,
    padded_transcript,
    run_stability,
    run_verbosity,
)
from eval.golden import GoldenSession
from eval.runner import JudgeRunner
from eval.schemas import CompetencyEvaluation, DimensionScore, SessionEvaluation
from rehearse_core.llm.fake import FakeProvider


def _canned(scores: dict[str, int] | None = None) -> SessionEvaluation:
    scores = scores or {"relevance": 4, "depth": 2, "evidence": 2, "communication": 4}
    dims = [
        DimensionScore(dimension=d, rationale="r", score=s, evidence_quotes=["q"])  # type: ignore[arg-type]
        for d, s in scores.items()
    ]
    mean = round(sum(scores.values()) / len(scores) * 2) / 2
    return SessionEvaluation(
        competency_evaluations=[
            CompetencyEvaluation(
                competency="RAG systems",
                dimension_scores=dims,
                competency_score=mean,
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
        turns=[
            {"speaker": "interviewer", "text": "Tell me about RAG."},
            {"speaker": "candidate", "text": "I fixed a two-document retrieval bug."},
        ],
    )


def test_pad_answer_keeps_the_original_and_only_adds_words() -> None:
    original = "I fixed a two-document retrieval bug."
    padded = pad_answer(original)
    assert original in padded
    assert len(padded) > len(original)


def test_padded_transcript_pads_candidate_turns_only() -> None:
    t = padded_transcript(_session())
    interviewer = next(text for speaker, text in t.turns if speaker == "interviewer")
    candidate = next(text for speaker, text in t.turns if speaker == "candidate")
    assert interviewer == "Tell me about RAG."  # untouched
    assert "I fixed a two-document retrieval bug." in candidate
    assert len(candidate) > len("I fixed a two-document retrieval bug.")


def test_dim_scores_casefolds_competency_names() -> None:
    ev = _canned()
    ev.competency_evaluations[0].competency = "RAG Systems"
    scores = _dim_scores(ev)
    assert "rag systems" in scores
    assert scores["rag systems"]["depth"] == 2


def test_shift_math_by_hand() -> None:
    s = _shift([0, 1, -1, 0, 2])
    assert s["n"] == 5
    assert s["mean_delta"] == pytest.approx(0.4)
    assert s["mean_abs_delta"] == pytest.approx(0.8)
    assert (s["increased"], s["decreased"], s["unchanged"]) == (2, 1, 2)


def test_stability_math_by_hand() -> None:
    s = _stability([[3, 3, 3], [2, 4, 3]])
    assert s["n_cells"] == 2
    assert s["max_std"] == pytest.approx(math.sqrt(2 / 3), abs=1e-3)
    assert s["mean_std"] == pytest.approx(math.sqrt(2 / 3) / 2, abs=1e-3)
    assert s["unanimous_share"] == pytest.approx(0.5)  # one of two cells was identical


def _wire_caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit, "_CACHE_DIR", tmp_path / "audit")
    monkeypatch.setattr(run_eval, "_CACHE_DIR", tmp_path / "judgements")


def test_verbosity_pipeline_reports_no_shift_for_a_steady_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A judge that returns the same scores no matter the input must show zero shift —
    # this exercises the whole pair-and-diff path without a network call.
    _wire_caches(tmp_path, monkeypatch)
    runner = JudgeRunner(FakeProvider(_canned()))
    report = run_verbosity(runner, [_session()])
    for dim in ("relevance", "depth", "evidence", "communication"):
        assert report["dimensions"][dim]["mean_delta"] == 0.0
        assert report["dimensions"][dim]["mean_abs_delta"] == 0.0


def test_stability_pipeline_reports_no_wander_for_a_steady_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wire_caches(tmp_path, monkeypatch)
    runner = JudgeRunner(FakeProvider(_canned()))
    report = run_stability(runner, [_session()], runs=3, canonical_temp=runner.temperature)
    assert report["runs"] == 3
    for dim in ("relevance", "depth", "evidence", "communication"):
        assert report["dimensions"][dim]["mean_std"] == 0.0
        assert report["dimensions"][dim]["unanimous_share"] == 1.0


def test_cache_key_separates_variant_and_temperature() -> None:
    a = audit._cache_path("t1", "padded", 0, 0.0, "claude-x", "abcdef0123456789")
    b = audit._cache_path("t1", "repeat", 0, 0.0, "claude-x", "abcdef0123456789")
    c = audit._cache_path("t1", "repeat", 0, 0.7, "claude-x", "abcdef0123456789")
    assert a.name != b.name  # different variant
    assert b.name != c.name  # different temperature
    assert "/" not in audit._cache_path("t1", "padded", 0, 0.0, "meta/x", "abc123").name
