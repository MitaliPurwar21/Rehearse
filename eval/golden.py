"""Loads the golden set — the hand-labeled transcripts the judge is graded against.

Format is one JSON object per line (see golden/schema.md). Each line is a session
with the human scores under "gold". We turn it into the same Transcript the runner
feeds the judge, so the only difference between "what the human said" and "what the
judge said" is who did the scoring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from eval.runner import Transcript

DIMENSIONS = ("relevance", "depth", "evidence", "communication")


class GoldCompetency(BaseModel):
    competency: str
    dimension_scores: dict[str, int]  # one of DIMENSIONS -> 1..5
    competency_score: float


class GoldenSession(BaseModel):
    session_id: str
    split: Literal["calibration", "validation"]
    job_description: str
    competencies: list[str]
    persona: str = "unspecified"
    turns: list[dict[str, str]]
    gold: list[GoldCompetency]

    def to_transcript(self) -> Transcript:
        return Transcript(
            job_description=self.job_description,
            competencies=self.competencies,
            turns=[(t["speaker"], t["text"]) for t in self.turns],
        )


def load_golden(path: Path, *, split: str | None = None) -> list[GoldenSession]:
    sessions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        session = GoldenSession.model_validate_json(line)
        if split is None or session.split == split:
            sessions.append(session)
    return sessions
