"""Runner wiring, no network. Feed it a fake provider with a canned result and
check it builds the prompt, stamps the metadata, and stays stable across calls.
"""

from eval.runner import JudgeRunner, Transcript
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
