"""Regression gate: did a change make the judge agree with the gold labels less?

Recomputes agreement from the FROZEN judge outputs (eval/golden/judgements.jsonl) using
the current code, and compares to eval/baseline.json. No API calls — safe to run in CI
on every change. Exits non-zero if agreement regressed beyond tolerance.

    python -m eval.check_regression

What it catches: bugs in the scoring / pairing / metrics code (e.g. a competency-match
change that silently drops data). It does NOT re-judge, so it won't catch a prompt change
on its own — for that, re-run eval.freeze_baseline (which calls the model) and review the
new baseline in the git diff.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.agreement import golden_path, summarize
from eval.golden import load_golden
from eval.schemas import SessionEvaluation

_JUDGEMENTS = Path(__file__).resolve().parent / "golden" / "judgements.jsonl"
_BASELINE = Path(__file__).resolve().parent / "baseline.json"

# How much worse than the baseline we tolerate before failing.
_QWK_DROP = 0.05  # overall QWK may fall at most this much
_MAE_RISE = 0.30  # any dimension's MAE may rise at most this much


def regressions(current: Any, baseline: Any) -> list[str]:
    """Return human-readable failures (empty list = gate passes).

    Both args are JSON-shaped agreement summaries (see eval.agreement.summarize).
    """
    failures: list[str] = []
    cur_qwk = current["overall"]["qwk"]
    base_qwk = baseline["overall"]["qwk"]
    if cur_qwk < base_qwk - _QWK_DROP:
        failures.append(f"overall QWK {cur_qwk} < baseline {base_qwk} - {_QWK_DROP}")

    for dim, stats in current["dimensions"].items():
        base = baseline["dimensions"].get(dim)
        if base and stats["mae"] > base["mae"] + _MAE_RISE:
            failures.append(f"{dim} MAE {stats['mae']} > baseline {base['mae']} + {_MAE_RISE}")
    return failures


def _load_judgements() -> dict[str, SessionEvaluation]:
    out: dict[str, SessionEvaluation] = {}
    for line in _JUDGEMENTS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["session_id"]] = SessionEvaluation.model_validate(row["evaluation"])
    return out


def main() -> None:
    if not _BASELINE.exists() or not _JUDGEMENTS.exists():
        raise SystemExit("No baseline yet. Run `python -m eval.freeze_baseline` first.")

    sessions = {s.session_id: s for s in load_golden(golden_path())}
    judgements = _load_judgements()
    results = [(sessions[sid], judgements[sid]) for sid in sessions if sid in judgements]
    if not results:
        raise SystemExit("Frozen judgements don't match the current golden set — re-freeze.")

    current = summarize(results)
    baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
    failures = regressions(current, baseline)

    print(
        f"baseline overall QWK {baseline['overall']['qwk']}  |  "
        f"current {current['overall']['qwk']}  (n_pairs={current['n_pairs']})"
    )
    if failures:
        print("\nREGRESSION GATE FAILED:")
        for note in failures:
            print(f"  - {note}")
        raise SystemExit(1)
    print("regression gate passed.")


if __name__ == "__main__":
    main()
