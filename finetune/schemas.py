"""Data shapes for the resume-to-JD fit scorer.

FitScore is the teacher's structured judgement of how well a resume matches a job.
It is also the exact schema the student model is trained to reproduce, so the same
model validates teacher labels, student predictions, and (later) API responses.

Pair / LabeledPair are the on-disk record shapes for the data pipeline: a Pair is a
generated resume tied to a job and an intended fit level (no score yet); a LabeledPair
adds the teacher's FitScore.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# Keep the skill lists bounded so a chatty teacher can't blow up token cost or produce
# a wall of near-duplicate skills.
_MAX_SKILLS = 15


class FitScore(BaseModel):
    """How well a resume matches a job. The training target."""

    overall_fit: int = Field(ge=0, le=100)  # headline 0-100 score
    skills_match: int = Field(ge=1, le=5)
    experience_match: int = Field(ge=1, le=5)
    seniority_match: int = Field(ge=1, le=5)
    matched_skills: list[str] = Field(max_length=_MAX_SKILLS)
    missing_skills: list[str] = Field(max_length=_MAX_SKILLS)
    rationale: str

    @field_validator("rationale")
    @classmethod
    def _rationale_present(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rationale must not be empty")
        return v

    @field_validator("matched_skills", "missing_skills")
    @classmethod
    def _clean_skills(cls, v: list[str]) -> list[str]:
        # Trim, drop blanks, de-dupe case-insensitively while keeping order.
        seen: set[str] = set()
        out: list[str] = []
        for s in v:
            s = s.strip()
            key = s.casefold()
            if s and key not in seen:
                seen.add(key)
                out.append(s)
        return out


class GeneratedResume(BaseModel):
    """A synthetic resume produced by the generator model."""

    resume_text: str

    @field_validator("resume_text")
    @classmethod
    def _resume_present(cls, v: str) -> str:
        if len(v.strip()) < 100:
            raise ValueError("resume_text looks too short to be a real resume")
        return v


class Pair(BaseModel):
    """A generated resume tied to a job and the fit level it was written for."""

    pair_id: str
    job_id: str
    fit_level: str
    resume_text: str


class LabeledPair(Pair):
    """A Pair with the teacher's fit score attached."""

    fit: FitScore
