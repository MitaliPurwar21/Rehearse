"""Print the frozen-judgement agreement as one JSON line.

This is what the Kubernetes operator's eval Job runs. It's the same offline computation
as the CI gate (recompute agreement from eval/golden/judgements.jsonl against the gold
labels, no model calls), but instead of a pass/fail it emits the numbers as JSON so the
operator can read them out of the pod logs and put them on the EvalRun's status.

    python -m eval.emit_agreement
    {"n_pairs": 408, "qwk": 0.827, "dimensions": {...}}
"""

from __future__ import annotations

import json

from eval.agreement import golden_path, summarize
from eval.check_regression import _load_judgements
from eval.golden import load_golden


def agreement_json() -> str:
    sessions = {s.session_id: s for s in load_golden(golden_path())}
    judgements = _load_judgements()
    results = [(sessions[sid], judgements[sid]) for sid in sessions if sid in judgements]
    if not results:
        raise SystemExit("frozen judgements don't match the golden set — re-freeze")
    summary = summarize(results)
    return json.dumps(
        {
            "n_pairs": summary["n_pairs"],
            "qwk": summary["overall"]["qwk"],
            "dimensions": {dim: stats["qwk"] for dim, stats in summary["dimensions"].items()},
        }
    )


def main() -> None:
    print(agreement_json())


if __name__ == "__main__":
    main()
