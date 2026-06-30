"""Extract competencies from a job description, schema-constrained.

One LLM call: feed it the JD, get back a JobProfile. Same provider seam as everything
else, so the output is validated by Pydantic and can't come back malformed.
"""

from __future__ import annotations

from ingestion.schemas import JobProfile
from rehearse_core.llm.base import LLMProvider

_SYSTEM = """You read a job description and extract the competencies an interviewer \
should assess for this role.

A competency is a specific, assessable skill area — not a generic trait.

Rules:
- Extract 4 to 6 competencies, the ones most central to this role.
- Each has a short name (2-4 words) and a one-sentence description grounded in the JD.
- Be specific to THIS role. Keep "Communication" or "Collaboration" only if the JD \
actually stresses it; drop filler like "team player", "passionate", "fast learner".
- Base everything on what the JD asks for, not generic assumptions about the title.
- Also pull out the role title and seniority if stated (leave seniority null if not).
"""


def extract_competencies(
    job_description: str,
    provider: LLMProvider,
    *,
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> JobProfile:
    if not job_description.strip():
        raise ValueError("empty job description")
    return provider.structured(
        system=_SYSTEM,
        user=job_description,
        schema=JobProfile,
        temperature=temperature,
        max_tokens=max_tokens,
    )
