"""The regression gate's pass/fail logic — tolerances behave as intended."""

from eval.check_regression import regressions


def _summary(overall_qwk: float, dim_mae: dict[str, float]) -> dict[str, object]:
    return {
        "n_pairs": 100,
        "overall": {"n": 100, "qwk": overall_qwk, "mae": 0.5, "spearman": 0.8, "exact": 0.6},
        "dimensions": {
            d: {"n": 25, "qwk": 0.8, "mae": m, "spearman": 0.8, "exact": 0.6}
            for d, m in dim_mae.items()
        },
    }


def test_passes_when_identical() -> None:
    base = _summary(0.83, {"depth": 0.34})
    assert regressions(_summary(0.83, {"depth": 0.34}), base) == []


def test_passes_within_tolerance() -> None:
    base = _summary(0.83, {"depth": 0.34})
    # QWK down 0.03 (< 0.05) and MAE up 0.16 (< 0.30): both inside tolerance.
    assert regressions(_summary(0.80, {"depth": 0.50}), base) == []


def test_fails_on_qwk_drop() -> None:
    base = _summary(0.83, {"depth": 0.34})
    fails = regressions(_summary(0.70, {"depth": 0.34}), base)  # QWK down 0.13
    assert any("QWK" in f for f in fails)


def test_fails_on_mae_rise() -> None:
    base = _summary(0.83, {"depth": 0.34})
    fails = regressions(_summary(0.83, {"depth": 0.80}), base)  # MAE up 0.46
    assert any("depth MAE" in f for f in fails)
