"""Freeze the current judge outputs and agreement as the regression baseline.

Run this intentionally when you've (re)judged the golden set and want to lock in the
result the CI gate compares against — e.g. after improving the judge prompt. It uses
the judged results (cached or live), so it may call the model.

    python -m eval.freeze_baseline

Writes (both committed):
  eval/golden/judgements.jsonl  — the judge's output per session
  eval/baseline.json            — the agreement numbers the gate checks against
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from eval.agreement import golden_path, summarize
from eval.golden import load_golden
from eval.run_eval import build_runner, judge_all

_JUDGEMENTS = Path(__file__).resolve().parent / "golden" / "judgements.jsonl"
_BASELINE = Path(__file__).resolve().parent / "baseline.json"


def main() -> None:
    path = golden_path()
    sessions = load_golden(path)
    if not sessions:
        raise SystemExit(f"No golden sessions in {path}")

    runner = build_runner()
    print(f"Judging {len(sessions)} sessions for the baseline ({runner.provider.model_id})...")
    results = judge_all(runner, sessions)

    with _JUDGEMENTS.open("w", encoding="utf-8") as f:
        for session, result in results:
            row = {"session_id": session.session_id, "evaluation": result.model_dump(mode="json")}
            f.write(json.dumps(row) + "\n")

    out: dict[str, object] = dict(summarize(results))
    out["meta"] = {
        "model_id": runner.provider.model_id,
        "prompt_hash": runner.prompt_hash,
        "golden_file": path.name,
        "n_sessions": len(results),
        "frozen_at": datetime.now(UTC).isoformat(),
    }
    _BASELINE.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    overall = out["overall"]
    assert isinstance(overall, dict)
    print(f"\nWrote {_JUDGEMENTS.name} ({len(results)} sessions) and {_BASELINE.name}")
    print(f"Baseline overall QWK = {overall['qwk']}")


if __name__ == "__main__":
    main()
