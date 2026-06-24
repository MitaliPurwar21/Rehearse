"""Quick end-to-end check against a real model. Not a unit test — it hits the
network, so run it by hand:

    python -m eval.smoke

Uses whatever JUDGE_PROVIDER points at (groq is free). The sample candidate is
deliberately vague and hand-wavy, so a working judge should mark depth and
evidence down.
"""

from __future__ import annotations

from eval.runner import JudgeRunner, Transcript
from rehearse_core.config import get_settings
from rehearse_core.llm.factory import build_judge_provider

_SAMPLE = Transcript(
    job_description=(
        "Senior ML Engineer. Build and operate RAG systems in production. Must debug "
        "live incidents and communicate clearly with non-ML stakeholders."
    ),
    competencies=["RAG systems", "Production debugging", "Communication"],
    turns=[
        ("interviewer", "Tell me about a RAG system you built and a problem you hit."),
        (
            "candidate",
            "We built a doc-QA bot. Retrieval was bad so I just turned up top_k to 50 and "
            "it kind of worked. I'm not totally sure why but the demo went fine.",
        ),
        ("interviewer", "How did you measure that it improved?"),
        ("candidate", "We didn't really measure it, it just felt better."),
    ],
)


def main() -> None:
    settings = get_settings()
    provider = build_judge_provider(settings)  # raises if the chosen provider's key is missing
    runner = JudgeRunner(
        provider,
        temperature=settings.judge_temperature,
        max_tokens=settings.judge_max_tokens,
    )
    result = runner.judge(_SAMPLE)
    assert result.model_meta is not None  # runner always stamps it

    print(f"model={result.model_meta.model_id}  prompt_hash={result.model_meta.prompt_hash[:12]}…")
    for comp in result.competency_evaluations:
        print(f"\n## {comp.competency}: {comp.competency_score}")
        for d in comp.dimension_scores:
            print(f"  {d.dimension:<14} {d.score}  — {d.rationale}")
    print(f"\nOverall: {result.overall_feedback}")


if __name__ == "__main__":
    main()
