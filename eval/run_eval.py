"""Run the judge over the golden set and print how well it agrees with my labels.

This is the live part — it calls the model, so run it by hand:

    python -m eval.run_eval

For each golden session it runs the judge, lines up the judge's dimension scores
with my hand scores by competency, and reports kappa / Spearman / MAE per dimension
and overall. With the tiny seed set the numbers are just a sanity check; they only
mean something once the real ~50-session golden set is labeled.
"""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path

from eval.golden import DIMENSIONS, load_golden
from eval.metrics import AgreementStats, compute_agreement, confusion
from eval.runner import JudgeRunner
from rehearse_core.config import get_settings
from rehearse_core.llm.factory import build_judge_provider

_GOLDEN = Path(__file__).resolve().parent / "golden" / "seed.jsonl"


def _print_row(name: str, a: AgreementStats) -> None:
    print(
        f"{name:<14} n={a.n:<3} QWK={a.qwk:+.2f} [{a.qwk_ci_low:+.2f},{a.qwk_ci_high:+.2f}]"
        f"  rho={a.spearman:+.2f}  MAE={a.mae:.2f}  exact={a.exact_match:.0%}"
    )


def main() -> None:
    settings = get_settings()
    sessions = load_golden(_GOLDEN)
    if not sessions:
        raise SystemExit(f"No golden sessions found in {_GOLDEN}")

    provider = build_judge_provider(settings)
    runner = JudgeRunner(
        provider,
        temperature=settings.judge_temperature,
        max_tokens=settings.judge_max_tokens,
    )

    human: dict[str, list[int]] = defaultdict(list)
    model: dict[str, list[int]] = defaultdict(list)

    print(f"Judging {len(sessions)} sessions with {provider.model_id}...")
    for i, session in enumerate(sessions, start=1):
        # Print before the call so you can see it working — each one is a network
        # round trip (more if the model needs a retry), so this isn't instant.
        label = f"  [{i}/{len(sessions)}] {session.session_id} ({session.persona}) ... "
        print(label, end="", flush=True)
        start = time.perf_counter()
        result = runner.judge(session.to_transcript())
        print(f"{time.perf_counter() - start:.1f}s")

        judged = {c.competency: c for c in result.competency_evaluations}
        for gold in session.gold:
            comp = judged.get(gold.competency)
            if comp is None:
                print(f"  ! judge skipped {gold.competency!r} in {session.session_id}")
                continue
            judge_dims = {d.dimension: d.score for d in comp.dimension_scores}
            for dim in DIMENSIONS:
                if dim in gold.dimension_scores and dim in judge_dims:
                    human[dim].append(gold.dimension_scores[dim])
                    model[dim].append(judge_dims[dim])

    all_human = [v for dim in DIMENSIONS for v in human[dim]]
    all_model = [v for dim in DIMENSIONS for v in model[dim]]
    if not all_human:
        raise SystemExit("No paired scores — did the judge return the right competencies?")

    print(f"\nGolden sessions: {len(sessions)}   paired scores: {len(all_human)}\n")
    _print_row("OVERALL", compute_agreement(all_human, all_model))
    for dim in DIMENSIONS:
        if human[dim]:
            _print_row(dim, compute_agreement(human[dim], model[dim]))

    print("\nOverall confusion (rows = my label 1..5, cols = judge):")
    for human_label, row in zip(range(1, 6), confusion(all_human, all_model), strict=True):
        print(f"  {human_label}: {row}")


if __name__ == "__main__":
    main()
