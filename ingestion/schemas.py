"""What we pull out of a job description.

A JobProfile is the role plus the competencies an interview should assess. These feed
the rest of the product: the interview asks about them, and the judge scores against
them. The judge already scores any competency on the four universal dimensions, so we
don't need a per-competency rubric here — just good, specific competencies.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Competency(BaseModel):
    name: str = Field(..., min_length=2, max_length=60, description="Short label, 2-4 words.")
    description: str = Field(..., description="What it covers, grounded in the JD.")


class JobProfile(BaseModel):
    role_title: str
    seniority: str | None = None  # e.g. "Senior", "Staff" — None if the JD doesn't say
    # 4-6 is the target; allow a little slack so a thin or dense JD still parses.
    competencies: list[Competency] = Field(..., min_length=3, max_length=8)
