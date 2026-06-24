"""Agreement stats between two sets of 1-5 scores (human gold vs the judge).

The scores are ordinal, so the main number is quadratic-weighted Cohen's kappa: it
punishes a 5-vs-1 miss far more than a 5-vs-4 one, which is what we want. The rest
(Spearman, MAE, exact-match, confusion) is supporting detail.

All functions take plain lists of ints in 1..5 and return plain floats, so they're
easy to test against hand-checked values.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import cohen_kappa_score, confusion_matrix

LABELS = [1, 2, 3, 4, 5]


@dataclass
class AgreementStats:
    n: int
    qwk: float
    qwk_ci_low: float
    qwk_ci_high: float
    spearman: float
    mae: float
    exact_match: float


def quadratic_weighted_kappa(human: list[int], model: list[int]) -> float:
    # When both sides are a single constant value sklearn returns nan, which isn't
    # useful. Treat identical-constant as perfect, differing-constant as no agreement.
    if len(set(human)) == 1 and len(set(model)) == 1:
        return 1.0 if human == model else 0.0
    k = cohen_kappa_score(human, model, weights="quadratic", labels=LABELS)
    return 0.0 if np.isnan(k) else float(k)


def spearman(human: list[int], model: list[int]) -> float:
    # spearmanr warns and returns nan if either side is constant — handle it first.
    if len(set(human)) == 1 or len(set(model)) == 1:
        return 0.0
    rho = spearmanr(human, model).correlation
    return 0.0 if np.isnan(rho) else float(rho)


def mae(human: list[int], model: list[int]) -> float:
    return float(np.mean(np.abs(np.array(human) - np.array(model))))


def exact_match(human: list[int], model: list[int]) -> float:
    return float(np.mean(np.array(human) == np.array(model)))


def confusion(human: list[int], model: list[int]) -> list[list[int]]:
    """Rows = human label 1..5, cols = judge label 1..5."""
    matrix: list[list[int]] = confusion_matrix(human, model, labels=LABELS).tolist()
    return matrix


def _bootstrap_kappa_ci(
    human: list[int], model: list[int], *, n_resamples: int, alpha: float, seed: int
) -> tuple[float, float]:
    # Resample (human, model) pairs with replacement and recompute kappa each time,
    # then take the middle 95%. Gives an honest sense of how shaky the number is on
    # a small sample — which ours always will be.
    rng = np.random.default_rng(seed)
    h = np.array(human)
    m = np.array(model)
    idx = np.arange(len(h))
    stats = []
    for _ in range(n_resamples):
        pick = rng.choice(idx, size=len(idx), replace=True)
        stats.append(quadratic_weighted_kappa(h[pick].tolist(), m[pick].tolist()))
    lo = float(np.percentile(stats, 100 * alpha / 2))
    hi = float(np.percentile(stats, 100 * (1 - alpha / 2)))
    return lo, hi


def compute_agreement(
    human: list[int],
    model: list[int],
    *,
    bootstrap: bool = True,
    n_resamples: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
) -> AgreementStats:
    if len(human) != len(model):
        raise ValueError(f"length mismatch: {len(human)} human vs {len(model)} model")
    if not human:
        raise ValueError("no scores to compare")

    qwk = quadratic_weighted_kappa(human, model)
    if bootstrap and len(human) > 1:
        lo, hi = _bootstrap_kappa_ci(
            human, model, n_resamples=n_resamples, alpha=alpha, seed=seed
        )
    else:
        lo, hi = qwk, qwk

    return AgreementStats(
        n=len(human),
        qwk=qwk,
        qwk_ci_low=lo,
        qwk_ci_high=hi,
        spearman=spearman(human, model),
        mae=mae(human, model),
        exact_match=exact_match(human, model),
    )
