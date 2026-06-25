"""Generator's pure helpers — assembling a session and numbering re-runs. The
model call itself isn't tested here (that needs the network)."""

import json
from pathlib import Path

from eval.generate import JOBS, PERSONAS, _GenTurn, _next_index, build_session


def test_personas_and_jobs_are_nonempty() -> None:
    assert len(JOBS) >= 2
    assert {"strong", "bullshitter", "off_topic"} <= set(PERSONAS)


def test_build_session_shape() -> None:
    turns = [
        _GenTurn(speaker="interviewer", text="Q?"),
        _GenTurn(speaker="candidate", text="A."),
    ]
    session = build_session(7, JOBS[0], "strong", turns, "validation")
    assert session["session_id"] == "gen_007"
    assert session["persona"] == "strong"
    assert session["competencies"] == JOBS[0]["competencies"]
    assert session["gold"] == []
    assert session["turns"] == [
        {"speaker": "interviewer", "text": "Q?"},
        {"speaker": "candidate", "text": "A."},
    ]


def test_next_index_starts_at_one(tmp_path: Path) -> None:
    assert _next_index(tmp_path / "missing.jsonl") == 1


def test_next_index_continues_past_existing(tmp_path: Path) -> None:
    path = tmp_path / "unlabeled.jsonl"
    lines = [
        json.dumps({"session_id": "gen_001"}),
        json.dumps({"session_id": "seed_u01"}),  # hand-authored, shouldn't count
        json.dumps({"session_id": "gen_002"}),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert _next_index(path) == 3
