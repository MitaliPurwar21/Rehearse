"""Turn (gold, judge) pairs into agreement numbers.

Kept separate from run_eval on purpose: this module imports no LLM providers, so
the CI regression gate can use it offline (no API key, no network).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TypedDict

from eval.golden import DIMENSIONS, GoldenSession
from eval.metrics import AgreementStats, compute_agreement
from eval.schemas import SessionEvaluation

Results = list[tuple[GoldenSession, SessionEvaluation]]

_GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


class DimStats(TypedDict):
    n: int
    qwk: float
    mae: float
    spearman: float
    exact: float


class AgreementSummary(TypedDict):
    n_pairs: int
    overall: DimStats
    dimensions: dict[str, DimStats]


def golden_path() -> Path:
    # Use the hand-labeled set once it exists; until then fall back to the seed.
    labeled = _GOLDEN_DIR / "labeled.jsonl"
    if labeled.exists() and labeled.stat().st_size > 0:
        return labeled
    return _GOLDEN_DIR / "seed.jsonl"


def pair_scores(results: Results) -> tuple[dict[str, list[int]], dict[str, list[int]], list[str]]:
    """Line up gold and judge dimension scores by competency.

    Match competency names case-insensitively — the judge sometimes title-cases
    them ('RAG systems' -> 'RAG Systems'), and an exact match would silently drop
    those, throwing away real data.
    """
    human: dict[str, list[int]] = defaultdict(list)
    model: dict[str, list[int]] = defaultdict(list)
    skipped: list[str] = []
    for session, result in results:
        judged = {c.competency.strip().casefold(): c for c in result.competency_evaluations}
        for gold in session.gold:
            comp = judged.get(gold.competency.strip().casefold())
            if comp is None:
                skipped.append(f"{gold.competency!r} in {session.session_id}")
                continue
            judge_dims = {d.dimension: d.score for d in comp.dimension_scores}
            for dim in DIMENSIONS:
                if dim in gold.dimension_scores and dim in judge_dims:
                    human[dim].append(gold.dimension_scores[dim])
                    model[dim].append(judge_dims[dim])
    return human, model, skipped


def _stats(a: AgreementStats) -> DimStats:
    return {
        "n": a.n,
        "qwk": round(a.qwk, 4),
        "mae": round(a.mae, 4),
        "spearman": round(a.spearman, 4),
        "exact": round(a.exact_match, 4),
    }


def summarize(results: Results) -> AgreementSummary:
    """Overall + per-dimension agreement as a plain dict (JSON-friendly).

    This is what we freeze as a baseline and what the regression gate compares
    against, so it must be deterministic — compute_agreement seeds its bootstrap.
    """
    human, model, _ = pair_scores(results)
    all_human = [v for dim in DIMENSIONS for v in human[dim]]
    all_model = [v for dim in DIMENSIONS for v in model[dim]]
    if not all_human:
        raise ValueError("no paired scores to summarize")

    dimensions = {
        dim: _stats(compute_agreement(human[dim], model[dim])) for dim in DIMENSIONS if human[dim]
    }
    return {
        "n_pairs": len(all_human),
        "overall": _stats(compute_agreement(all_human, all_model)),
        "dimensions": dimensions,
    }
