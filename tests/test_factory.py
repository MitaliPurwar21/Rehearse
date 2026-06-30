"""Factory picks the right provider and complains clearly when the key's missing.
No network here — building a provider just makes the client, it doesn't call out.
"""

import pytest

from rehearse_core.config import Settings
from rehearse_core.llm.claude import ClaudeProvider
from rehearse_core.llm.factory import build_provider
from rehearse_core.llm.groq import GroqProvider


def test_claude_selected_when_provider_is_claude() -> None:
    s = Settings(judge_provider="claude", anthropic_api_key="sk-test")
    assert isinstance(build_provider(s), ClaudeProvider)


def test_groq_selected_when_provider_is_groq() -> None:
    s = Settings(judge_provider="groq", groq_api_key="gsk-test")
    assert isinstance(build_provider(s), GroqProvider)


def test_missing_key_raises_systemexit() -> None:
    s = Settings(judge_provider="groq", groq_api_key=None)
    with pytest.raises(SystemExit):
        build_provider(s)
