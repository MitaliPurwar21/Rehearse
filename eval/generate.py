"""Generate synthetic interview transcripts to label.

The model plays candidates of different quality across a few job descriptions, and
we write the transcripts WITHOUT scores to golden/unlabeled.jsonl. You then score
them by hand with label.py.

Generating the candidate and scoring it are kept separate on purpose: if the same
model did both, we'd be grading the model against itself, which proves nothing.

Run it when you have API budget (the free Groq tier has a daily token cap):

    python -m eval.generate --per-combo 3

Appends to whatever is already in unlabeled.jsonl, so you can build the set up over
a few runs.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Literal, TypedDict

from pydantic import BaseModel

from rehearse_core.config import get_settings
from rehearse_core.llm.factory import build_judge_provider  # same provider seam as the judge

_OUT = Path(__file__).resolve().parent / "golden" / "unlabeled.jsonl"


class Job(TypedDict):
    role: str
    job_description: str
    competencies: list[str]


# A few roles to spread the golden set across. Keep the competencies short — they're
# what the interviewer probes and what gets scored.
JOBS: list[Job] = [
    {
        "role": "Senior ML Engineer",
        "job_description": (
            "Senior ML Engineer. Build and run RAG systems in production and "
            "communicate clearly with non-ML stakeholders."
        ),
        "competencies": ["RAG systems", "Communication"],
    },
    {
        "role": "Data Scientist",
        "job_description": (
            "Data Scientist. Design and analyze experiments (A/B tests) and explain "
            "results and tradeoffs to product teams."
        ),
        "competencies": ["Experiment design", "Communication"],
    },
    {
        "role": "Backend Engineer",
        "job_description": (
            "Backend Engineer. Design and operate reliable APIs and debug production "
            "incidents under pressure."
        ),
        "competencies": ["API design", "Production debugging"],
    },
]

# What each candidate type should sound like. The labeler never sees these — they're
# only here to get a spread of answer quality into the set.
PERSONAS = {
    "strong": "excellent: specific, gives metrics, discusses tradeoffs and failure modes",
    "mediocre": "average: knows the basics but stays shallow and vague on specifics",
    "bullshitter": "confident and fluent but vague, light on real substance or evidence",
    "terse": "correct and concrete but very brief, almost too short",
    "off_topic": "talks up soft skills and enthusiasm, barely answers the question",
}


class _GenTurn(BaseModel):
    speaker: Literal["interviewer", "candidate"]
    text: str


class _GenTranscript(BaseModel):
    turns: list[_GenTurn]


def _system() -> str:
    return (
        "You write realistic mock-interview transcripts. Given a role, the "
        "competencies being probed, and a candidate type, produce a short transcript "
        "(3 to 4 interviewer/candidate exchanges) that honestly reflects that "
        "candidate type. The interviewer asks focused questions; the candidate answers "
        "in their own voice. Output only the dialogue — no scores or commentary."
    )


def _user(role: str, jd: str, competencies: list[str], persona_desc: str) -> str:
    return (
        f"Role: {role}\n"
        f"Job description: {jd}\n"
        f"Competencies to probe: {', '.join(competencies)}\n"
        f"Candidate type: {persona_desc}\n\n"
        "Write the transcript."
    )


def build_session(
    idx: int, job: Job, persona: str, turns: list[_GenTurn], split: str
) -> dict[str, object]:
    return {
        "session_id": f"gen_{idx:03d}",
        "split": split,
        "persona": persona,
        "job_description": job["job_description"],
        "competencies": job["competencies"],
        "turns": [{"speaker": t.speaker, "text": t.text} for t in turns],
        "gold": [],
    }


def _next_index(path: Path) -> int:
    # Continue numbering past any gen_NNN already in the file so re-runs don't clash.
    if not path.exists():
        return 1
    used = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line)["session_id"].startswith("gen_"):
            used += 1
    return used + 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate transcripts to label.")
    parser.add_argument("--per-combo", type=int, default=3, help="transcripts per job x persona")
    parser.add_argument("--seed", type=int, default=0, help="seed for the train/val split")
    args = parser.parse_args()

    settings = get_settings()
    provider = build_judge_provider(settings)
    rng = random.Random(args.seed)
    system = _system()
    idx = _next_index(_OUT)
    written = 0

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    with _OUT.open("a", encoding="utf-8") as f:
        for job in JOBS:
            for persona, desc in PERSONAS.items():
                for _ in range(args.per_combo):
                    transcript = provider.structured(
                        system=system,
                        user=_user(job["role"], job["job_description"], job["competencies"], desc),
                        schema=_GenTranscript,
                        temperature=0.9,  # high on purpose — we want varied candidates
                        max_tokens=1200,
                    )
                    split = "calibration" if rng.random() < 0.3 else "validation"
                    session = build_session(idx, job, persona, transcript.turns, split)
                    f.write(json.dumps(session) + "\n")
                    print(f"  wrote {session['session_id']} ({persona}, {job['role']})", flush=True)
                    idx += 1
                    written += 1

    print(f"\nWrote {written} transcripts to {_OUT}")


if __name__ == "__main__":
    main()
