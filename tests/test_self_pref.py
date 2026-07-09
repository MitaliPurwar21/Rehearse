"""Self-preference probe, offline. The pure math (lifts + difference-in-differences)
and transcript assembly are checked by hand; the full round-robin is run with fake
providers that hand back canned answers/judgements, so no network and no keys."""

from pathlib import Path

import pytest
from pydantic import BaseModel

import eval.self_pref as self_pref
from eval.generate import JOBS
from eval.runner import JudgeRunner
from eval.schemas import CompetencyEvaluation, DimensionScore, SessionEvaluation
from eval.self_pref import (
    AnswerSet,
    assemble_transcript,
    mean_competency_score,
    questions_for,
    self_preference,
)


class _Fake:
    """Returns one canned object, but only for the schema it was built for — so the
    same instance can't accidentally satisfy both a generation and a judging call."""

    def __init__(self, model_id: str, response: BaseModel) -> None:
        self.model_id = model_id
        self._response = response

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> BaseModel:
        if not isinstance(self._response, schema):
            got = type(self._response).__name__
            raise TypeError(f"fake has {got}, asked for {schema.__name__}")
        return self._response


def _canned_eval(v: int) -> SessionEvaluation:
    # RAG systems + Communication, matching the first job's competencies. All four
    # dimensions get the same value so the competency score is consistent with them.
    def comp(name: str) -> CompetencyEvaluation:
        dims = [
            DimensionScore(dimension=d, rationale="r", score=v, evidence_quotes=["q"])  # type: ignore[arg-type]
            for d in ("relevance", "depth", "evidence", "communication")
        ]
        return CompetencyEvaluation(
            competency=name, dimension_scores=dims, competency_score=float(v), summary_feedback="ok"
        )

    return SessionEvaluation(
        competency_evaluations=[comp("RAG systems"), comp("Communication")],
        overall_feedback="fine",
    )


def test_questions_are_one_per_competency() -> None:
    job = JOBS[0]
    qs = questions_for(job)
    assert len(qs) == len(job["competencies"])
    assert all(comp in q for comp, q in zip(job["competencies"], qs, strict=True))


def test_assemble_transcript_interleaves_and_pairs_to_shorter() -> None:
    job = JOBS[0]
    qs = ["Q1", "Q2"]
    t = assemble_transcript(job, qs, ["A1"])  # only one answer -> one exchange
    assert t.turns == [("interviewer", "Q1"), ("candidate", "A1")]
    assert t.competencies == job["competencies"]


def test_mean_competency_score_reads_each_competency() -> None:
    assert mean_competency_score(_canned_eval(4)) == [4.0, 4.0]


def test_self_preference_difference_in_differences_by_hand() -> None:
    matrix = {
        ("claude", "claude"): 4.0,
        ("claude", "groq"): 3.0,  # Claude judge prefers Claude answers by 1.0
        ("groq", "claude"): 3.5,
        ("groq", "groq"): 3.5,  # Groq judge is indifferent
    }
    p = self_preference(matrix)
    assert p["lift_claude_judge"] == pytest.approx(1.0)
    assert p["lift_groq_judge"] == pytest.approx(0.0)
    assert p["self_preference"] == pytest.approx(1.0)  # the extra boost, not real quality


def test_round_robin_reports_zero_preference_when_judges_are_neutral(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Both judges give every answer the same score, so no cell can differ -> DiD is 0.
    monkeypatch.setattr(self_pref, "_CACHE_DIR", tmp_path / "selfpref")
    answers = AnswerSet(answers=["ans one", "ans two"])
    authors = {
        "claude": _Fake("claude-x", answers),
        "groq": _Fake("groq-x", answers),
    }
    judges = {
        "claude": JudgeRunner(_Fake("claude-x", _canned_eval(4))),  # type: ignore[arg-type]
        "groq": JudgeRunner(_Fake("groq-x", _canned_eval(4))),  # type: ignore[arg-type]
    }
    report = self_pref.run_self_pref(authors, judges, per_job=1)  # type: ignore[arg-type]

    pref = report["preference"]
    assert isinstance(pref, dict)
    assert pref["self_preference"] == 0.0
    scores = report["mean_scores"]
    assert isinstance(scores, dict)
    assert set(scores.values()) == {4.0}  # every cell identical
