"""Swappable LLM provider interface.

Everything that calls an LLM goes through LLMProvider, so we can swap Claude for
Groq (or a fake in tests) without touching the call sites.
"""

from rehearse_core.llm.base import LLMProvider
from rehearse_core.llm.fake import FakeProvider

__all__ = ["LLMProvider", "FakeProvider"]
