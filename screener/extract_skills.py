"""Pull the concrete required skills out of a job description.

The competencies from ingestion are high-level ("LLM Application Development"), which makes
a gap report vague. This grabs the specific, checkable things a JD asks for (tools, stacks,
platforms, domains) so the fit score can say what's actually missing. It also matches the
granular skill shape the fit scorer was trained on.
"""

from __future__ import annotations

from rehearse_core.llm.base import LLMProvider

from .schemas import RequiredSkills

_SYSTEM = """You read a job description and list the concrete skills it asks for.

- required: the specific tools, technologies, languages, platforms, and domain areas the
  role needs (for example "FastAPI", "Railway", "MCP servers", "education data"). Be
  specific and granular, pulled from the whole posting, not high-level themes.
- nice_to_have: the skills the posting frames as a bonus or a plus.
Use short skill names. Skip soft-skill filler like "team player" or "fast learner"."""


def extract_required_skills(
    jd_text: str,
    provider: LLMProvider,
    *,
    temperature: float = 0.0,
    max_tokens: int = 1024,
) -> RequiredSkills:
    if not jd_text.strip():
        raise ValueError("empty job description")
    return provider.structured(
        system=_SYSTEM,
        user=jd_text,
        schema=RequiredSkills,
        temperature=temperature,
        max_tokens=max_tokens,
    )
