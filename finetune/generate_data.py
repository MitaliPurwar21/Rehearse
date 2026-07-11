"""Generate synthetic resumes to score.

For each job posting and each fit level we ask a cheap model (Haiku by default) to write
a realistic resume. The output has NO score attached: generating the resume and scoring it
are kept separate, the same way eval/generate.py keeps candidate-writing separate from
judging, so the teacher isn't grading text it also wrote.

Resumes are written to finetune/data/pairs.jsonl (append, resumable). Run label_data.py
next to score them.

    python -m finetune.generate_data --sample 20        # cheap eyeball batch first
    python -m finetune.generate_data --per-combo 40      # the full set
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Iterator
from pathlib import Path

from pydantic import ValidationError

from rehearse_core.config import get_settings
from rehearse_core.llm.base import LLMProvider
from rehearse_core.llm.claude import ClaudeProvider

from .jobs import FIT_LEVELS, JOBS, JobPosting
from .schemas import GeneratedResume, Pair

DATA_DIR = Path(__file__).resolve().parent / "data"
PAIRS_PATH = DATA_DIR / "pairs.jsonl"

# Haiku is plenty for writing plausible resumes, and its output tokens are the cheap part.
DEFAULT_GEN_MODEL = "claude-haiku-4-5"


def _system() -> str:
    return (
        "You write realistic, concise resumes for job candidates. Given a role and a "
        "description of how well the candidate fits it, write a plausible one-page resume "
        "for exactly that kind of candidate: a summary, 2 to 3 work experiences with a few "
        "bullet points each, a skills line, and education. Keep it around 350 to 450 words. "
        "Do not mention the job posting, do not rate the candidate, and do not explain your "
        "choices. Output only the resume text."
    )


def _user(job: JobPosting, fit_desc: str) -> str:
    return (
        f"Target role: {job['role']} ({job['seniority']} level)\n"
        f"Required skills for the role: {', '.join(job['required_skills'])}\n"
        f"Write a resume for this kind of candidate: {fit_desc}\n\n"
        "Write the resume."
    )


def _combos() -> list[tuple[JobPosting, str, str]]:
    return [(job, level, desc) for job in JOBS for level, desc in FIT_LEVELS.items()]


def _generate_one(
    provider: LLMProvider, job: JobPosting, desc: str, temperature: float, retries: int = 3
) -> GeneratedResume | None:
    # The model sometimes returns an empty or too-short tool call. Retry a couple of times,
    # then give up on this one so a single bad response can't kill a long run.
    for attempt in range(retries):
        try:
            return provider.structured(
                system=_system(),
                user=_user(job, desc),
                schema=GeneratedResume,
                temperature=temperature,
                max_tokens=900,
            )
        except ValidationError:
            if attempt == retries - 1:
                return None
    return None


def generate_pairs(
    provider: LLMProvider,
    *,
    per_combo: int,
    sample: int | None,
    start_idx: int,
    temperature: float,
    rng: random.Random,
) -> Iterator[Pair]:
    """Yield generated Pairs.

    sample, if given, caps the total count and spreads it across combos (a quick,
    cheap batch to eyeball). Otherwise every combo gets per_combo resumes.
    """
    combos = _combos()
    rng.shuffle(combos)
    idx = start_idx
    made = 0
    rounds = per_combo if sample is None else sample
    for r in range(rounds):
        for job, level, desc in combos:
            if sample is not None and made >= sample:
                return
            if sample is None and r >= per_combo:
                return
            resume = _generate_one(provider, job, desc, temperature)
            if resume is None:
                print(f"  skip ({level}, {job['job_id']}): empty output", file=sys.stderr)
                continue
            yield Pair(
                pair_id=f"pair_{idx:04d}",
                job_id=job["job_id"],
                fit_level=level,
                resume_text=resume.resume_text.strip(),
            )
            idx += 1
            made += 1


def _existing_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic resumes to score.")
    parser.add_argument("--per-combo", type=int, default=40, help="resumes per job x fit level")
    parser.add_argument("--sample", type=int, default=None, help="cap total (quick eyeball batch)")
    parser.add_argument("--model", default=DEFAULT_GEN_MODEL, help="generation model id")
    parser.add_argument("--temperature", type=float, default=0.9, help="high for varied resumes")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set.")
    provider = ClaudeProvider(api_key=settings.anthropic_api_key, model_id=args.model)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    start_idx = _existing_count(PAIRS_PATH) + 1
    written = 0
    with PAIRS_PATH.open("a", encoding="utf-8") as f:
        for pair in generate_pairs(
            provider,
            per_combo=args.per_combo,
            sample=args.sample,
            start_idx=start_idx,
            temperature=args.temperature,
            rng=random.Random(args.seed),
        ):
            f.write(json.dumps(pair.model_dump()) + "\n")
            f.flush()
            written += 1
            print(f"  wrote {pair.pair_id} ({pair.fit_level}, {pair.job_id})", flush=True)

    print(f"\nWrote {written} resumes to {PAIRS_PATH} (model {args.model}).")


if __name__ == "__main__":
    main()
