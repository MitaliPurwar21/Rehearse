"""Shapes for the candidate-side screener.

ResumeProfile is what we parse out of a raw resume (the mirror of ingestion's JobProfile
for a JD). GapReport is the candidate-facing view of a fit score: what you match, what the
role wants that you're missing, and a plain-English summary.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResumeProfile(BaseModel):
    name: str | None = None
    summary: str = Field(..., description="One or two lines on who this candidate is.")
    skills: list[str] = Field(..., min_length=1, description="Concrete skills the resume shows.")
    years_experience: float | None = None
    titles: list[str] = Field(default_factory=list, description="Recent job titles, newest first.")


class GapReport(BaseModel):
    overall_fit: int = Field(ge=0, le=100)
    strengths: list[str]  # required skills the resume covers
    gaps: list[str]  # required skills the resume is missing
    summary: str


class QuestionSet(BaseModel):
    questions: list[str] = Field(..., min_length=1, max_length=10)


class RequiredSkills(BaseModel):
    """The concrete skills a JD asks for, granular enough to make gaps meaningful."""

    required: list[str] = Field(..., min_length=1, max_length=25)
    nice_to_have: list[str] = Field(default_factory=list, max_length=25)
