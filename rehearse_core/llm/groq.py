"""Groq provider — the free fallback.

Same idea as the Claude one, just over Groq's OpenAI-style API: give it a function
whose params are our schema, force the call, validate the JSON it hands back.

Fine for free wiring checks. Don't calibrate the real judge on a small free model
though — that needs something stronger.
"""

from __future__ import annotations

from typing import Any, TypeVar, cast

from groq import Groq
from groq.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionNamedToolChoiceParam,
    ChatCompletionToolParam,
)
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_TOOL_NAME = "emit_result"


class GroqProvider:
    def __init__(self, *, api_key: str, model_id: str) -> None:
        if not api_key:
            raise ValueError("GroqProvider requires an api_key (set GROQ_API_KEY).")
        self.model_id = model_id
        self._client = Groq(api_key=api_key)

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> T:
        # Same casting dance as the Claude provider — the SDK's tool types are
        # stricter than the plain dicts we build here.
        tool = cast(
            ChatCompletionToolParam,
            {
                "type": "function",
                "function": {
                    "name": _TOOL_NAME,
                    "description": "Return the result in the required structured format.",
                    "parameters": cast(Any, schema.model_json_schema()),
                },
            },
        )
        tool_choice: ChatCompletionNamedToolChoiceParam = {
            "type": "function",
            "function": {"name": _TOOL_NAME},
        }
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        resp = self._client.chat.completions.create(
            model=self.model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=messages,
            tools=[tool],
            tool_choice=tool_choice,
        )
        tool_calls = resp.choices[0].message.tool_calls
        if not tool_calls:
            raise ValueError("Groq did not return a tool call for structured output.")
        arguments = tool_calls[0].function.arguments
        return schema.model_validate_json(arguments)
