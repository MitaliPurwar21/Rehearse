"""Environment-driven configuration, shared across services.

All secrets and model choices come from the environment (or a local .env file),
never hard-coded. Import ``get_settings()`` rather than constructing Settings
directly so the parsed config is cached.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM providers ---
    anthropic_api_key: str | None = None
    groq_api_key: str | None = None

    # --- Judge (eval harness) ---
    # Default to a strong Claude model since the judge needs to be reliable.
    # JUDGE_PROVIDER=groq runs free for wiring checks — just don't calibrate the
    # real judge on a small free model.
    judge_provider: Literal["claude", "groq"] = "claude"
    judge_model: str = "claude-sonnet-4-6"  # used when judge_provider=claude
    groq_model: str = "llama-3.3-70b-versatile"  # used when judge_provider=groq
    judge_temperature: float = 0.0
    judge_max_tokens: int = 4096

    # --- Observability (hooked up later) ---
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
