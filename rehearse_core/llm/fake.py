"""Test provider: hands back a canned response, never touches the network.

Lets us run the whole harness in CI with no key and no cost.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class FakeProvider:
    model_id = "fake-provider"

    def __init__(self, response: BaseModel) -> None:
        self._response = response
        # Captured so tests can assert on what the runner sent.
        self.last_system: str | None = None
        self.last_user: str | None = None

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> T:
        self.last_system = system
        self.last_user = user
        if not isinstance(self._response, schema):
            raise TypeError(
                f"FakeProvider was given a {type(self._response).__name__} but the "
                f"caller requested schema {schema.__name__}."
            )
        return self._response
