"""Hand-score the generated transcripts to build the golden set.

Shows you one transcript at a time plus the rubric, you type four scores (1-5) per
competency, and it writes the labeled result to golden/labeled.jsonl. The candidate
type ("persona") is deliberately hidden while you score so it doesn't bias you.

    python -m eval.label

Stop anytime by typing q — progress is saved and you pick up where you left off,
since it skips any session already in labeled.jsonl.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from eval.golden import DIMENSIONS, GoldCompetency, GoldenSession, load_golden

_GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
_UNLABELED = _GOLDEN_DIR / "unlabeled.jsonl"
_LABELED = _GOLDEN_DIR / "labeled.jsonl"
_RUBRIC = Path(__file__).resolve().parent / "rubric.yaml"


def competency_score(dimension_scores: dict[str, int]) -> float:
    """Mean of the four dimension scores, rounded to the nearest 0.5."""
    mean = sum(dimension_scores.values()) / len(dimension_scores)
    return round(mean * 2) / 2


def _already_labeled() -> set[str]:
    if not _LABELED.exists():
        return set()
    return {
        GoldenSession.model_validate_json(line).session_id
        for line in _LABELED.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _print_rubric() -> None:
    rubric = yaml.safe_load(_RUBRIC.read_text(encoding="utf-8"))
    print("\nScore each dimension 1-5 against these anchors:")
    for dim, body in rubric["dimensions"].items():
        print(f"\n  {dim} — {body['description']}")
        for score, text in body["anchors"].items():
            print(f"     {score}: {text}")


def _ask_score(dim: str) -> int | None:
    while True:
        raw = input(f"    {dim} (1-5, or q to stop): ").strip().lower()
        if raw == "q":
            return None
        if raw in {"1", "2", "3", "4", "5"}:
            return int(raw)
        print("    please type a number 1-5 (or q)")


def _label_session(session: GoldenSession) -> GoldenSession | None:
    print("\n" + "=" * 72)
    print(f"Session {session.session_id}\n")
    print(f"JOB:\n{session.job_description}\n")
    print("TRANSCRIPT:")
    for turn in session.turns:
        print(f"  {turn['speaker'].upper()}: {turn['text']}")

    gold = []
    total = len(session.competencies)
    for n, competency in enumerate(session.competencies, start=1):
        print(f"\n--- competency {n} of {total}: {competency} ---")
        print(f"    Score ONLY how well the candidate showed '{competency}'.")
        print("    A great answer to a different question still scores low here.")
        scores: dict[str, int] = {}
        for dim in DIMENSIONS:
            value = _ask_score(dim)
            if value is None:
                return None
            scores[dim] = value
        gold.append(
            GoldCompetency(
                competency=competency,
                dimension_scores=scores,
                competency_score=competency_score(scores),
            )
        )
    return session.model_copy(update={"gold": gold})


def main() -> None:
    if not _UNLABELED.exists():
        raise SystemExit(
            f"No transcripts at {_UNLABELED}. Generate some first: python -m eval.generate"
        )

    sessions = load_golden(_UNLABELED)
    done = _already_labeled()
    todo = [s for s in sessions if s.session_id not in done]
    if not todo:
        print("Everything in unlabeled.jsonl is already labeled. Nothing to do.")
        return

    print(f"{len(todo)} transcripts to label ({len(done)} already done).")
    _print_rubric()

    with _LABELED.open("a", encoding="utf-8") as f:
        for i, session in enumerate(todo, start=1):
            print(f"\n[{i}/{len(todo)}]")
            labeled = _label_session(session)
            if labeled is None:
                print("\nStopped — progress saved. Run again to continue.")
                break
            f.write(labeled.model_dump_json() + "\n")
            f.flush()
            print(f"  saved {session.session_id}")

    print(f"\nLabeled set: {_LABELED}")


if __name__ == "__main__":
    main()
