"""Generate interview questions tailored to one candidate and one role.

This touches the interviewer side, not the judge: it feeds the candidate's resume and the
role's required skills to the model and asks for questions that probe THIS candidate, both
the strengths they claim and the gaps against the role.
"""

from __future__ import annotations

from finetune.jobs import JobPosting
from rehearse_core.llm.base import LLMProvider

from .schemas import QuestionSet

_SYSTEM = """You are a technical interviewer preparing for a specific candidate.

Given the role's required skills and the candidate's resume, write interview questions
tailored to this candidate: press on the strengths they claim so they have to show real
depth, and probe the gaps against the role to see how they handle what they haven't done.
Ground each question in something concrete from the resume or the role. No generic
questions, no trivia."""


def generate_questions(
    resume_text: str,
    job: JobPosting,
    provider: LLMProvider,
    *,
    n: int = 5,
    temperature: float = 0.4,
    max_tokens: int = 1024,
) -> QuestionSet:
    if not resume_text.strip():
        raise ValueError("empty resume")
    user = (
        f"ROLE: {job['role']} ({job['seniority']})\n"
        f"Required skills: {', '.join(job['required_skills'])}\n\n"
        f"RESUME:\n{resume_text}\n\n"
        f"Write {n} interview questions tailored to this candidate."
    )
    return provider.structured(
        system=_SYSTEM,
        user=user,
        schema=QuestionSet,
        temperature=temperature,
        max_tokens=max_tokens,
    )
