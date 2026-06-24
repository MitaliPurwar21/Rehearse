"""Runner wiring, no network. Feed it a fake provider with a canned result and
check it builds the prompt, stamps the metadata, and stays stable across calls.
"""

from typing import TypeVar

import pytest
from pydantic import BaseModel, ValidationError

from eval.runner import JudgeRunner, Transcript
from eval.schemas import CompetencyEvaluation, DimensionScore, SessionEvaluation
from rehearse_core.llm.fake import FakeProvider

_T = TypeVar("_T", bound=BaseModel)


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


def _transcript() -> Transcript:
    return Transcript(
        job_description="Senior ML Engineer building RAG.",
        competencies=["RAG systems"],
        turns=[("interviewer", "Tell me about RAG."), ("candidate", "I raised top_k.")],
    )


def test_judge_returns_validated_result_and_stamps_meta() -> None:
    provider = FakeProvider(_canned())
    runner = JudgeRunner(provider)
    result = runner.judge(_transcript())

    assert result.model_meta is not None
    assert result.model_meta.model_id == "fake-provider"
    assert result.model_meta.prompt_hash == runner.prompt_hash
    assert result.model_meta.rubric_version == 1


def test_user_message_includes_jd_competencies_and_turns() -> None:
    provider = FakeProvider(_canned())
    JudgeRunner(provider).judge(_transcript())

    assert provider.last_user is not None
    assert "Senior ML Engineer" in provider.last_user
    assert "RAG systems" in provider.last_user
    assert "CANDIDATE: I raised top_k." in provider.last_user


def test_prompt_hash_is_stable() -> None:
    runner = JudgeRunner(FakeProvider(_canned()))
    assert runner.prompt_hash == JudgeRunner(FakeProvider(_canned())).prompt_hash
    assert len(runner.prompt_hash) == 64


def _a_validation_error() -> ValidationError:
    # A 5 with no quotes is exactly what the judge sometimes returns and what the
    # schema rejects — reuse that to simulate a bad model response.
    try:
        DimensionScore(dimension="depth", rationale="r", score=5, evidence_quotes=[])
    except ValidationError as err:
        return err
    raise AssertionError("expected a ValidationError")


class _FlakyProvider:
    """Fails validation a set number of times, then returns a good response."""

    model_id = "flaky"

    def __init__(self, fail_times: int, response: SessionEvaluation) -> None:
        self.fail_times = fail_times
        self.response = response
        self.calls = 0

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[_T],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> _T:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise _a_validation_error()
        if not isinstance(self.response, schema):
            raise TypeError("unexpected schema in test")
        return self.response


def test_judge_retries_then_succeeds() -> None:
    provider = _FlakyProvider(fail_times=1, response=_canned())
    result = JudgeRunner(provider).judge(_transcript())
    assert provider.calls == 2
    assert result.model_meta is not None and result.model_meta.model_id == "flaky"


def test_judge_gives_up_after_max_attempts() -> None:
    provider = _FlakyProvider(fail_times=99, response=_canned())
    with pytest.raises(RuntimeError, match="failed schema validation"):
        JudgeRunner(provider).judge(_transcript(), max_attempts=2)
    assert provider.calls == 2
