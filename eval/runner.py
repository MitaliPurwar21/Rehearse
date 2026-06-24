"""Takes an interview transcript and gets it scored.

Loads the judge prompt + rubric, builds the message we send the model, calls
whatever provider it was handed, and stamps the result with which model/prompt
produced it. The prompt_hash is the part CI cares about: change the prompt and the
hash changes, so a regression can't sneak through.

Doesn't care which provider it gets — real Claude/Groq in practice, the fake one
in tests.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from eval.schemas import JudgeMeta, SessionEvaluation
from rehearse_core.llm.base import LLMProvider

_EVAL_DIR = Path(__file__).resolve().parent
_DEFAULT_PROMPT = _EVAL_DIR / "judge_prompt.md"
_DEFAULT_RUBRIC = _EVAL_DIR / "rubric.yaml"

# Tacked onto the message when a retry is needed. Weaker models sometimes skip the
# quotes or drop a dimension; this nudges them to fix exactly that.
_RETRY_HINT = (
    "\n\nYour previous answer was rejected because it didn't match the required "
    "format:\n{error}\nTry again. Score every competency on all four dimensions, and "
    "include at least one verbatim quote for any dimension scored 2, 4, or 5."
)


@dataclass(frozen=True)
class Transcript:
    """A single interview session to be judged."""

    job_description: str
    competencies: list[str]
    # Ordered (speaker, text) turns, e.g. ("interviewer", "..."), ("candidate", "...").
    turns: list[tuple[str, str]]


class JudgeRunner:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        prompt_path: Path = _DEFAULT_PROMPT,
        rubric_path: Path = _DEFAULT_RUBRIC,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> None:
        self.provider = provider
        self.system = prompt_path.read_text(encoding="utf-8")
        rubric = yaml.safe_load(rubric_path.read_text(encoding="utf-8"))
        self.rubric_version = int(rubric["version"])
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    def prompt_hash(self) -> str:
        """Fingerprint of the exact prompt text; CI compares against this."""
        return hashlib.sha256(self.system.encode("utf-8")).hexdigest()

    def _render_user(self, t: Transcript) -> str:
        competencies = "\n".join(f"- {c}" for c in t.competencies)
        turns = "\n".join(f"{speaker.upper()}: {text}" for speaker, text in t.turns)
        return (
            "## JOB DESCRIPTION\n"
            f"{t.job_description}\n\n"
            "## COMPETENCIES TO ASSESS\n"
            f"{competencies}\n\n"
            "## INTERVIEW TRANSCRIPT\n"
            f"{turns}\n"
        )

    def judge(self, transcript: Transcript, *, max_attempts: int = 3) -> SessionEvaluation:
        base_user = self._render_user(transcript)
        last_error: ValidationError | None = None

        for _attempt in range(max_attempts):
            user = base_user
            if last_error is not None:
                user = base_user + _RETRY_HINT.format(error=last_error)
            try:
                result = self.provider.structured(
                    system=self.system,
                    user=user,
                    schema=SessionEvaluation,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
            except ValidationError as err:
                last_error = err
                continue

            result.model_meta = JudgeMeta(
                model_id=self.provider.model_id,
                prompt_hash=self.prompt_hash,
                temperature=self.temperature,
                rubric_version=self.rubric_version,
            )
            return result

        raise RuntimeError(
            f"judge output failed schema validation after {max_attempts} attempts; "
            f"last error:\n{last_error}"
        )
