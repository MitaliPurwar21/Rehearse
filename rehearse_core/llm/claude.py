"""Claude provider. Structured output via tool use.

The trick: hand Claude a single tool whose input schema is our Pydantic model and
force it to call that tool. Whatever it passes as the tool arguments is our
payload, which we validate on the way out.
"""

from __future__ import annotations

from typing import Any, TypeVar, cast

from anthropic import Anthropic
from anthropic.types import MessageParam, ToolChoiceToolParam, ToolParam
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_TOOL_NAME = "emit_result"


class ClaudeProvider:
    def __init__(self, *, api_key: str, model_id: str) -> None:
        if not api_key:
            raise ValueError("ClaudeProvider requires an api_key (set ANTHROPIC_API_KEY).")
        self.model_id = model_id
        self._client = Anthropic(api_key=api_key)

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> T:
        # The SDK has its own TypedDicts for these; plain dicts upset mypy, so cast.
        tool = cast(
            ToolParam,
            {
                "name": _TOOL_NAME,
                "description": "Return the result in the required structured format.",
                "input_schema": cast(Any, schema.model_json_schema()),
            },
        )
        tool_choice: ToolChoiceToolParam = {"type": "tool", "name": _TOOL_NAME}
        messages: list[MessageParam] = [{"role": "user", "content": user}]
        resp = self._client.messages.create(
            model=self.model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            tools=[tool],
            tool_choice=tool_choice,
            messages=messages,
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == _TOOL_NAME:
                return schema.model_validate(block.input)
        # Shouldn't happen with forced tool_choice, but fail loudly if it does.
        raise ValueError(
            f"Claude did not return a '{_TOOL_NAME}' tool call; got blocks: "
            f"{[b.type for b in resp.content]}"
        )
