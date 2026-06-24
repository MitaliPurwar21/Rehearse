"""Tests for the agreement math. The whole project rests on these numbers being
right, so check them against cases I can work out by hand."""

import math

from eval.metrics import (
    compute_agreement,
    confusion,
    exact_match,
    mae,
    quadratic_weighted_kappa,
    spearman,
)


def test_perfect_agreement() -> None:
    a = [1, 2, 3, 4, 5, 3, 2]
    stats = compute_agreement(a, a)
    assert stats.qwk == 1.0
    assert stats.spearman == 1.0
    assert stats.mae == 0.0
    assert stats.exact_match == 1.0
    # every bootstrap resample is also perfect, so the interval collapses to 1.0
    assert stats.qwk_ci_low == 1.0 and stats.qwk_ci_high == 1.0


def test_mae_and_exact_match_by_hand() -> None:
    human = [1, 1, 5]
    model = [2, 3, 5]
    assert mae(human, model) == (1 + 2 + 0) / 3
    assert exact_match(human, model) == 1 / 3


def test_kappa_penalizes_far_misses_more() -> None:
    truth = [1, 2, 3, 4, 5]
    near = [2, 3, 4, 5, 4]   # off by 1
    far = [5, 4, 1, 2, 1]    # off by a lot
    assert quadratic_weighted_kappa(truth, near) > quadratic_weighted_kappa(truth, far)


def test_kappa_in_range() -> None:
    k = quadratic_weighted_kappa([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])
    assert -1.0 <= k <= 1.0


def test_spearman_monotonic_is_one() -> None:
    # strictly increasing together -> rank correlation 1
    assert math.isclose(spearman([1, 2, 3, 4], [2, 3, 4, 5]), 1.0)


def test_constant_inputs_dont_crash() -> None:
    assert quadratic_weighted_kappa([3, 3, 3], [3, 3, 3]) == 1.0
    assert quadratic_weighted_kappa([3, 3, 3], [4, 4, 4]) == 0.0
    assert spearman([3, 3, 3], [1, 2, 3]) == 0.0  # undefined -> 0, no crash


def test_confusion_shape_and_counts() -> None:
    m = confusion([1, 1, 5], [1, 2, 5])
    assert len(m) == 5 and all(len(row) == 5 for row in m)
    assert m[0][0] == 1  # one (human=1, judge=1)
    assert m[0][1] == 1  # one (human=1, judge=2)
    assert m[4][4] == 1  # one (human=5, judge=5)
