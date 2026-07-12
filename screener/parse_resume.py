"""Parse a raw resume into a ResumeProfile, schema-constrained.

One LLM call through the same provider seam as everything else, so the output is validated
by Pydantic. This is the mirror of ingestion's JD -> JobProfile: here it's resume -> profile.
"""

from __future__ import annotations

from rehearse_core.llm.base import LLMProvider

from .schemas import ResumeProfile

_SYSTEM = """You read a resume and pull out a short structured profile.

Rules:
- summary: one or two lines on who this candidate is and their focus.
- skills: the concrete, checkable skills the resume actually shows (tools, languages,
  systems). Skip soft-skill filler like "team player" or "fast learner".
- years_experience: total years of relevant professional experience if you can tell, else null.
- titles: recent job titles, most recent first.
- name: the candidate's name if present, else null.
Base everything on what the resume says, not assumptions."""


def parse_resume(
    resume_text: str,
    provider: LLMProvider,
    *,
    temperature: float = 0.0,
    max_tokens: int = 1024,
) -> ResumeProfile:
    if not resume_text.strip():
        raise ValueError("empty resume")
    return provider.structured(
        system=_SYSTEM,
        user=resume_text,
        schema=ResumeProfile,
        temperature=temperature,
        max_tokens=max_tokens,
    )
