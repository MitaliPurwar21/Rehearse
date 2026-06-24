"""The one LLM interface everything goes through.

For the harness (and most of the app) we only need one thing: structured output.
Give a provider a system prompt, a user message and a Pydantic schema, get back a
validated instance of that schema.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    """Anything that can return schema-constrained structured output."""

    model_id: str

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> T:
        """Return a validated instance of ``schema``.

        Raise if the model output can't be coerced into a valid one — callers count
        on getting a good object back, not None.
        """
        ...
