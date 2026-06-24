"""Picks the judge provider from settings.

One place to choose, so the smoke test and the real harness pick the same way.
Concrete providers are imported lazily — you only need the SDK for the one you
actually use.
"""

from __future__ import annotations

from rehearse_core.config import Settings
from rehearse_core.llm.base import LLMProvider


def build_judge_provider(settings: Settings) -> LLMProvider:
    if settings.judge_provider == "groq":
        from rehearse_core.llm.groq import GroqProvider

        if not settings.groq_api_key:
            raise SystemExit("JUDGE_PROVIDER=groq but GROQ_API_KEY is not set.")
        return GroqProvider(api_key=settings.groq_api_key, model_id=settings.groq_model)

    from rehearse_core.llm.claude import ClaudeProvider

    if not settings.anthropic_api_key:
        raise SystemExit("JUDGE_PROVIDER=claude but ANTHROPIC_API_KEY is not set.")
    return ClaudeProvider(api_key=settings.anthropic_api_key, model_id=settings.judge_model)
