"""The labeler is mostly interactive, but the scoring rule is pure — test that."""

from eval.label import competency_score


def test_competency_score_is_mean_rounded_to_half() -> None:
    assert competency_score({"relevance": 4, "depth": 2, "evidence": 2, "communication": 4}) == 3.0
    assert competency_score({"relevance": 3, "depth": 3, "evidence": 3, "communication": 3}) == 3.0
    assert competency_score({"relevance": 5, "depth": 5, "evidence": 4, "communication": 4}) == 4.5
    assert competency_score({"relevance": 3, "depth": 3, "evidence": 2, "communication": 2}) == 2.5


def test_competency_score_matches_schema_tolerance() -> None:
    # The score it produces must satisfy the CompetencyEvaluation mean check
    # (within 0.51 of the true mean), so labeler output is always schema-valid.
    dims = {"relevance": 5, "depth": 2, "evidence": 2, "communication": 4}
    true_mean = sum(dims.values()) / len(dims)
    assert abs(competency_score(dims) - true_mean) <= 0.51
