"""The seed golden file should parse and convert cleanly into transcripts."""

from pathlib import Path

from eval.golden import DIMENSIONS, load_golden

_GOLDEN_DIR = Path(__file__).resolve().parents[1] / "eval" / "golden"
_SEED = _GOLDEN_DIR / "seed.jsonl"
_UNLABELED = _GOLDEN_DIR / "unlabeled.jsonl"


def test_seed_loads() -> None:
    sessions = load_golden(_SEED)
    assert len(sessions) == 5
    assert {s.persona for s in sessions} >= {"strong", "bullshitter", "off_topic"}


def test_gold_scores_are_in_range_and_complete() -> None:
    for session in load_golden(_SEED):
        for gold in session.gold:
            assert set(gold.dimension_scores) == set(DIMENSIONS)
            assert all(1 <= v <= 5 for v in gold.dimension_scores.values())


def test_split_filter() -> None:
    cal = load_golden(_SEED, split="calibration")
    val = load_golden(_SEED, split="validation")
    assert len(cal) + len(val) == 5
    assert all(s.split == "validation" for s in val)


def test_to_transcript_roundtrip() -> None:
    session = load_golden(_SEED)[0]
    t = session.to_transcript()
    assert t.competencies == session.competencies
    assert t.turns[0][0] == "interviewer"
    assert isinstance(t.turns[0][1], str)


def test_unlabeled_starter_parses_and_is_unlabeled() -> None:
    sessions = load_golden(_UNLABELED)
    assert len(sessions) == 6
    # No gold scores yet, so nothing should count as labeled.
    assert all(not s.is_labeled for s in sessions)
    assert all(s.gold == [] for s in sessions)
