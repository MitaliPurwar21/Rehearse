"""Score generated resumes with the teacher model.

Sonnet reads each (job, resume) pair and returns a FitScore. These labels are the ground
truth the student model is trained to reproduce, so this is the step where label quality
matters and we pay for the stronger model.

Reads finetune/data/pairs.jsonl, writes finetune/data/labeled.jsonl. Resumable: pairs
already in labeled.jsonl are skipped, so a re-run only labels what's left.

    python -m finetune.label_data --limit 20     # score the sample first, eyeball it
    python -m finetune.label_data                # score everything not yet labeled
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path

from pydantic import ValidationError

from rehearse_core.config import get_settings
from rehearse_core.llm.base import LLMProvider
from rehearse_core.llm.claude import ClaudeProvider

from .generate_data import DATA_DIR, PAIRS_PATH
from .jobs import JOBS, JobPosting
from .schemas import FitScore, LabeledPair, Pair

LABELED_PATH = DATA_DIR / "labeled.jsonl"

DEFAULT_LABEL_MODEL = "claude-sonnet-4-6"

_JOBS_BY_ID: dict[str, JobPosting] = {job["job_id"]: job for job in JOBS}


def _system() -> str:
    return (
        "You are a technical recruiter scoring how well a resume matches a job. Be strict "
        "and ground every judgement in what the resume actually says, not what it implies.\n\n"
        "Return these fields:\n"
        "- overall_fit (0-100): the headline match. 80-100 strong hire, 60-79 worth a call, "
        "40-59 weak, 0-39 not a fit.\n"
        "- skills_match (1-5): how many required skills the resume clearly demonstrates. "
        "5 = nearly all with depth, 3 = about half, 1 = almost none.\n"
        "- experience_match (1-5): relevance and depth of experience for this exact role.\n"
        "- seniority_match (1-5): how well the candidate's level fits the role's level. "
        "5 = right level, lower for clearly under- or over-qualified.\n"
        "- matched_skills: required skills the resume clearly shows.\n"
        "- missing_skills: required skills the resume does not show.\n"
        "- rationale: 2 to 3 sentences explaining the scores. No fluff.\n\n"
        "In matched_skills and missing_skills, use clean skill names only, with no "
        "parenthetical commentary. Put all nuance in the rationale.\n"
        "matched_skills and missing_skills together should cover the role's required skills."
    )


def _user(job: JobPosting, resume_text: str) -> str:
    return (
        f"JOB\n"
        f"Role: {job['role']} ({job['seniority']} level)\n"
        f"Required skills: {', '.join(job['required_skills'])}\n"
        f"Nice to have: {', '.join(job['nice_to_have'])}\n"
        f"Description: {job['jd_text']}\n\n"
        f"RESUME\n{resume_text}\n\n"
        "Score this resume against the job."
    )


def prompt_for(job: JobPosting, resume_text: str) -> tuple[str, str]:
    """The (system, user) prompt used to score a pair.

    Reused by prepare.py so the student model is trained on the same prompt shape the
    teacher saw, which is also what we'll serve at inference.
    """
    return _system(), _user(job, resume_text)


def label_pair(provider: LLMProvider, job: JobPosting, pair: Pair) -> LabeledPair:
    fit = provider.structured(
        system=_system(),
        user=_user(job, pair.resume_text),
        schema=FitScore,
        temperature=0.0,
        max_tokens=700,
    )
    return LabeledPair(**pair.model_dump(), fit=fit)


def _read_pairs(path: Path) -> list[Pair]:
    if not path.exists():
        return []
    pairs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            pairs.append(Pair.model_validate_json(line))
    return pairs


def _already_labeled(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ids.add(json.loads(line)["pair_id"])
    return ids


def _label_sync(todo: list[Pair], model: str, api_key: str) -> Iterator[LabeledPair]:
    provider = ClaudeProvider(api_key=api_key, model_id=model)
    for pair in todo:
        job = _JOBS_BY_ID.get(pair.job_id)
        if job is None:
            print(f"  skip {pair.pair_id}: unknown job_id {pair.job_id}", flush=True)
            continue
        # Retry a bad tool call a couple of times, then skip so one response can't stop the run.
        for attempt in range(3):
            try:
                yield label_pair(provider, job, pair)
                break
            except ValidationError:
                if attempt == 2:
                    print(f"  skip {pair.pair_id}: bad label after retries", file=sys.stderr)


def _label_batch(
    todo: list[Pair], all_pairs: list[Pair], model: str, api_key: str, poll_seconds: int
) -> Iterator[LabeledPair]:
    # Imported lazily so the sync path (and the tests) don't need the batch code loaded.
    from anthropic import Anthropic

    from .batch_label import run_batch

    client = Anthropic(api_key=api_key)
    lookup = {p.pair_id: p for p in all_pairs}
    for pair, fit in run_batch(client, todo, lookup, _JOBS_BY_ID, model, poll_seconds):
        yield LabeledPair(**pair.model_dump(), fit=fit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score resumes with the teacher model.")
    parser.add_argument("--limit", type=int, default=None, help="score at most this many")
    parser.add_argument("--model", default=DEFAULT_LABEL_MODEL, help="teacher model id")
    parser.add_argument(
        "--batch", action="store_true", help="use the Batches API (50%% cheaper, async)"
    )
    parser.add_argument("--poll-seconds", type=int, default=15, help="batch poll interval")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set.")
    key = settings.anthropic_api_key

    pairs = _read_pairs(PAIRS_PATH)
    done = _already_labeled(LABELED_PATH)
    todo = [p for p in pairs if p.pair_id not in done]
    if args.limit is not None:
        todo = todo[: args.limit]
    if not todo:
        print("Nothing to label (all pairs already scored, or no pairs generated yet).")
        return

    if args.batch:
        results = _label_batch(todo, pairs, args.model, key, args.poll_seconds)
    else:
        results = _label_sync(todo, args.model, key)

    LABELED_PATH.parent.mkdir(parents=True, exist_ok=True)
    labeled = 0
    with LABELED_PATH.open("a", encoding="utf-8") as f:
        for result in results:
            # Guard against re-emitting a pair (a resumed batch re-reads all results).
            if result.pair_id in done:
                continue
            done.add(result.pair_id)
            f.write(json.dumps(result.model_dump()) + "\n")
            f.flush()
            labeled += 1
            print(
                f"  {result.pair_id} ({result.fit_level}, {result.job_id}) "
                f"-> fit {result.fit.overall_fit}",
                flush=True,
            )

    print(f"\nLabeled {labeled} pairs into {LABELED_PATH} (model {args.model}).")


if __name__ == "__main__":
    main()
