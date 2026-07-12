"""Score a resume against a job into a FitScore.

Reuses the exact prompt the fit scorer was trained on (finetune.label_data.prompt_for), so
the same call works whether the provider is Claude (the teacher) or the fine-tuned local
model. That's the whole point of matching the training prompt: the model is a drop-in here.
"""

from __future__ import annotations

from finetune.jobs import JobPosting
from finetune.label_data import prompt_for
from finetune.schemas import FitScore
from rehearse_core.llm.base import LLMProvider


def score_fit(
    resume_text: str,
    job: JobPosting,
    provider: LLMProvider,
    *,
    temperature: float = 0.0,
    max_tokens: int = 700,
) -> FitScore:
    if not resume_text.strip():
        raise ValueError("empty resume")
    system, user = prompt_for(job, resume_text)
    return provider.structured(
        system=system,
        user=user,
        schema=FitScore,
        temperature=temperature,
        max_tokens=max_tokens,
    )
