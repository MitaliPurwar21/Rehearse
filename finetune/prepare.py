"""Split labeled data into train/val/test and format it for training.

Reads finetune/data/labeled.jsonl and writes train.jsonl / val.jsonl / test.jsonl. The
split is stratified by fit level so each split gets a spread of scores, and it's seeded so
it's reproducible. Each output row carries both the training view (prompt + completion) and
the raw view (resume + fit) so Phase 3 can score predictions without re-deriving anything.

    python -m finetune.prepare                    # default 80/10/10 split
    python -m finetune.prepare --val 0.1 --test 0.1
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from .generate_data import DATA_DIR
from .jobs import JOBS, JobPosting
from .label_data import LABELED_PATH, prompt_for
from .schemas import LabeledPair

_JOBS_BY_ID: dict[str, JobPosting] = {job["job_id"]: job for job in JOBS}

SPLITS = ("train", "val", "test")


def _read_labeled(path: Path) -> list[LabeledPair]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(LabeledPair.model_validate_json(line))
    return out


def split_records(
    records: list[LabeledPair], *, seed: int, val_frac: float, test_frac: float
) -> dict[str, list[LabeledPair]]:
    """Stratified split by fit level. Deterministic given seed.

    Stratifying keeps the same spread of fit levels in every split, so the test set is a
    fair sample and no fit level lands entirely in training.
    """
    if val_frac + test_frac >= 1.0:
        raise ValueError("val_frac + test_frac must be < 1.0")
    rng = random.Random(seed)
    by_level: dict[str, list[LabeledPair]] = defaultdict(list)
    for r in records:
        by_level[r.fit_level].append(r)

    out: dict[str, list[LabeledPair]] = {s: [] for s in SPLITS}
    for level in sorted(by_level):
        group = by_level[level]
        rng.shuffle(group)
        n = len(group)
        n_test = round(n * test_frac)
        n_val = round(n * val_frac)
        out["test"].extend(group[:n_test])
        out["val"].extend(group[n_test : n_test + n_val])
        out["train"].extend(group[n_test + n_val :])
    return out


def to_row(record: LabeledPair, split: str) -> dict[str, object]:
    """One output record: training view (prompt/completion) plus the raw view."""
    job = _JOBS_BY_ID[record.job_id]
    system, user = prompt_for(job, record.resume_text)
    completion = record.fit.model_dump_json()
    return {
        "pair_id": record.pair_id,
        "job_id": record.job_id,
        "fit_level": record.fit_level,
        "split": split,
        "system": system,
        "prompt": user,
        "completion": completion,
        "resume_text": record.resume_text,
        "fit": record.fit.model_dump(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Split and format labeled data.")
    parser.add_argument("--val", type=float, default=0.1, help="validation fraction")
    parser.add_argument("--test", type=float, default=0.1, help="test fraction")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    records = _read_labeled(LABELED_PATH)
    if not records:
        raise SystemExit(f"No labeled data at {LABELED_PATH}. Run label_data.py first.")

    splits = split_records(records, seed=args.seed, val_frac=args.val, test_frac=args.test)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        path = DATA_DIR / f"{split}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for record in splits[split]:
                f.write(json.dumps(to_row(record, split)) + "\n")
        print(f"  {split}: {len(splits[split])} rows -> {path}")

    total = sum(len(v) for v in splits.values())
    print(f"\nSplit {total} labeled pairs into train/val/test.")


if __name__ == "__main__":
    main()
