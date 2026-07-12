"""Phase 3: how well the fine-tuned student agrees with the teacher on the test split.

Reads the held-out test labels (finetune/data/test.jsonl) and the student's raw generations
(predictions.jsonl, one {pair_id, raw} per line, produced in Colab). Parses each generation
into a FitScore, aligns with the teacher by pair_id, and reports agreement per sub-score with
the same metrics used for the judge (QWK, MAE, exact match). overall_fit is 0-100, so it gets
MAE and Spearman instead of QWK.

    python -m finetune.eval_screener                       # default paths
    python -m finetune.eval_screener --preds other.jsonl
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from eval.metrics import AgreementStats, compute_agreement, mae, spearman

from .generate_data import DATA_DIR
from .schemas import FitScore

TEST_PATH = DATA_DIR / "test.jsonl"
PREDS_PATH = DATA_DIR / "predictions.jsonl"

SUBDIMS = ("skills_match", "experience_match", "seniority_match")


def extract_fit(raw: str) -> FitScore | None:
    """Pull a FitScore out of a raw generation. Returns None if it can't be parsed.

    The model usually emits clean JSON, but be forgiving: if there's stray text around it,
    fall back to the span from the first '{' to the last '}'.
    """
    text = raw.strip()
    candidates = [text]
    if "{" in text and "}" in text:
        candidates.append(text[text.index("{") : text.rindex("}") + 1])
    for c in candidates:
        try:
            return FitScore.model_validate_json(c)
        except (ValidationError, ValueError):
            continue
    return None


@dataclass
class ScreenerReport:
    n_test: int
    n_predicted: int
    n_parsed: int
    subdims: dict[str, AgreementStats]
    overall_mae: float
    overall_spearman: float

    @property
    def parse_rate(self) -> float:
        return self.n_parsed / self.n_test if self.n_test else 0.0


def _read_test(path: Path) -> list[dict[str, object]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _read_preds(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["pair_id"]] = row["raw"]
    return out


def evaluate(test: list[dict[str, object]], preds: dict[str, str]) -> ScreenerReport:
    teacher: dict[str, FitScore] = {
        str(row["pair_id"]): FitScore.model_validate(row["fit"]) for row in test
    }
    student: dict[str, FitScore] = {}
    n_predicted = 0
    for pid in teacher:
        raw = preds.get(pid)
        if raw is None:
            continue
        n_predicted += 1
        fit = extract_fit(raw)
        if fit is not None:
            student[pid] = fit

    ids = [pid for pid in teacher if pid in student]
    subdims: dict[str, AgreementStats] = {}
    for dim in SUBDIMS:
        human = [int(getattr(teacher[i], dim)) for i in ids]
        model = [int(getattr(student[i], dim)) for i in ids]
        subdims[dim] = compute_agreement(human, model)

    overall_h = [teacher[i].overall_fit for i in ids]
    overall_m = [student[i].overall_fit for i in ids]
    return ScreenerReport(
        n_test=len(test),
        n_predicted=n_predicted,
        n_parsed=len(ids),
        subdims=subdims,
        overall_mae=mae(overall_h, overall_m),
        overall_spearman=spearman(overall_h, overall_m),
    )


def print_report(report: ScreenerReport) -> None:
    print("Distilled scorer vs teacher (held-out test split)")
    parsed = f"{report.n_parsed}/{report.n_test} ({report.parse_rate:.1%})"
    print(f"n={report.n_test}, parsed {parsed}\n")
    print(f"{'dimension':<18}{'QWK':>7}{'95% CI':>16}{'MAE':>7}{'exact':>8}")
    for dim, s in report.subdims.items():
        ci = f"[{s.qwk_ci_low:.2f}, {s.qwk_ci_high:.2f}]"
        print(f"{dim:<18}{s.qwk:>7.2f}{ci:>16}{s.mae:>7.2f}{s.exact_match:>7.0%}")
    print(
        f"\noverall_fit (0-100): MAE {report.overall_mae:.1f}, "
        f"Spearman {report.overall_spearman:.2f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Score the fine-tuned model against the teacher.")
    parser.add_argument("--test", default=str(TEST_PATH))
    parser.add_argument("--preds", default=str(PREDS_PATH))
    args = parser.parse_args()

    test = _read_test(Path(args.test))
    preds = _read_preds(Path(args.preds))
    if not preds:
        raise SystemExit(f"No predictions at {args.preds}. Generate them in Colab first.")
    print_report(evaluate(test, preds))


if __name__ == "__main__":
    main()
