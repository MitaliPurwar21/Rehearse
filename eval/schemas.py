"""Output shapes for the LLM judge.

The judge has to return data in these exact shapes (we force that with tool use),
and the golden set is labeled with the same structure so the two line up directly.
Scores are on the four dimensions in rubric.yaml; the competency score is just
their mean.

A couple of choices worth calling out:
- rationale sits before score so the model reasons first and picks the number
  second. It scores more sensibly that way than if you ask for the digit up front.
- evidence_quotes are verbatim from the transcript. They double as the "show me
  where" bit in the product and as the judge's grounding.
- JudgeMeta records the model + prompt hash, which is what CI watches so a prompt
  change can't slip by unnoticed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Dimension = Literal["relevance", "depth", "evidence", "communication"]


class DimensionScore(BaseModel):
    """One dimension's 1-5 score plus the quotes backing it up."""

    dimension: Dimension
    rationale: str = Field(..., description="Why this score, referencing the anchors.")
    score: int = Field(..., ge=1, le=5)
    evidence_quotes: list[str] = Field(
        default_factory=list,
        description="Verbatim spans from the transcript supporting the score.",
    )

    @model_validator(mode="after")
    def _require_evidence_for_substantive_scores(self) -> DimensionScore:
        # Make the model back up its scores. A 2/4/5 says the candidate said
        # something specific, so it has to quote it. A 1 (off-topic, or nothing
        # there to quote) or a neutral 3 can skip it.
        if self.score not in (1, 3) and not self.evidence_quotes:
            raise ValueError(
                f"dimension '{self.dimension}' scored {self.score} but provided "
                "no evidence_quotes (required for scores 2, 4, and 5)"
            )
        return self


class CompetencyEvaluation(BaseModel):
    """One competency scored across all four dimensions."""

    competency: str
    dimension_scores: list[DimensionScore]
    competency_score: float = Field(..., ge=1, le=5)
    summary_feedback: str

    @model_validator(mode="after")
    def _scores_cover_all_dimensions(self) -> CompetencyEvaluation:
        seen = {d.dimension for d in self.dimension_scores}
        expected: set[str] = {"relevance", "depth", "evidence", "communication"}
        if seen != expected:
            missing = expected - seen
            extra = seen - expected
            raise ValueError(
                f"competency '{self.competency}' dimension coverage mismatch; "
                f"missing={sorted(missing)} extra={sorted(extra)}"
            )
        return self

    @model_validator(mode="after")
    def _competency_score_matches_mean(self) -> CompetencyEvaluation:
        # rubric.yaml says the competency score is the mean of the dimensions.
        # Check the model actually did that instead of handing back some number it
        # liked. Loose tolerance so a rounded value (2.5 for [2,2,3,3]) still passes.
        mean = sum(d.score for d in self.dimension_scores) / len(self.dimension_scores)
        if abs(mean - self.competency_score) > 0.51:
            raise ValueError(
                f"competency '{self.competency}' score {self.competency_score} is "
                f"inconsistent with dimension mean {mean:.2f} (unweighted_mean rule)"
            )
        return self


class JudgeMeta(BaseModel):
    """Which model and prompt produced a run, so CI can catch drift."""

    model_id: str
    prompt_hash: str = Field(..., description="SHA-256 of the rendered judge prompt.")
    temperature: float = 0.0
    rubric_version: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SessionEvaluation(BaseModel):
    """The judge's full output for one interview."""

    competency_evaluations: list[CompetencyEvaluation]
    overall_feedback: str
    model_meta: JudgeMeta | None = None  # attached by the runner, not the model
