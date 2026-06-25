"""Run the judge over the golden set and report how well it agrees with my labels.

This is the live part — it calls the model, so run it by hand:

    python -m eval.run_eval

Each session's judge result is cached to .cache/, keyed by the model and the prompt
hash. So if it dies partway (a rate limit on the free tier, a network blip), nothing
is lost — re-run the same command and it picks up where it stopped, only calling the
model for sessions it hasn't judged yet. That also lets you judge a big set in chunks
across a few days if you're on a daily token cap.

It lines up the judge's dimension scores with my hand scores by competency and reports
kappa / Spearman / MAE per dimension and overall.
"""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path

from eval.golden import DIMENSIONS, GoldenSession, load_golden
from eval.metrics import AgreementStats, compute_agreement, confusion
from eval.runner import JudgeRunner
from eval.schemas import SessionEvaluation
from rehearse_core.config import get_settings
from rehearse_core.llm.factory import build_judge_provider

# Catch whichever provider's rate-limit error is installed, without hard-coupling
# this module to a specific SDK.
_RATE_LIMIT_ERRORS: tuple[type[BaseException], ...] = ()
try:
    from groq import RateLimitError as _GroqRateLimit

    _RATE_LIMIT_ERRORS += (_GroqRateLimit,)
except ImportError:  # pragma: no cover
    pass
try:
    from anthropic import RateLimitError as _AnthropicRateLimit

    _RATE_LIMIT_ERRORS += (_AnthropicRateLimit,)
except ImportError:  # pragma: no cover
    pass

_GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
_CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "judgements"


def _golden_path() -> Path:
    # Use your hand-labeled set once it exists; until then fall back to the seed.
    labeled = _GOLDEN_DIR / "labeled.jsonl"
    if labeled.exists() and labeled.stat().st_size > 0:
        return labeled
    return _GOLDEN_DIR / "seed.jsonl"


def _cache_path(session_id: str, model_id: str, prompt_hash: str) -> Path:
    safe_model = model_id.replace("/", "-")  # some model ids have slashes
    return _CACHE_DIR / f"{session_id}__{safe_model}__{prompt_hash[:12]}.json"


def _judge_or_cache(runner: JudgeRunner, session: GoldenSession) -> tuple[SessionEvaluation, bool]:
    """Return (result, was_cached). Judges and caches on a miss."""
    path = _cache_path(session.session_id, runner.provider.model_id, runner.prompt_hash)
    if path.exists():
        return SessionEvaluation.model_validate_json(path.read_text(encoding="utf-8")), True
    result = runner.judge(session.to_transcript())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(), encoding="utf-8")
    return result, False


def _print_row(name: str, a: AgreementStats) -> None:
    print(
        f"{name:<14} n={a.n:<3} QWK={a.qwk:+.2f} [{a.qwk_ci_low:+.2f},{a.qwk_ci_high:+.2f}]"
        f"  rho={a.spearman:+.2f}  MAE={a.mae:.2f}  exact={a.exact_match:.0%}"
    )


def main() -> None:
    settings = get_settings()
    golden_path = _golden_path()
    sessions = load_golden(golden_path)
    if not sessions:
        raise SystemExit(f"No golden sessions found in {golden_path}")

    provider = build_judge_provider(settings)
    runner = JudgeRunner(
        provider,
        temperature=settings.judge_temperature,
        max_tokens=settings.judge_max_tokens,
    )

    print(f"Golden set: {golden_path.name}")
    print(f"Judging {len(sessions)} sessions with {provider.model_id} (cached results reused)...")

    results: list[tuple[GoldenSession, SessionEvaluation]] = []
    try:
        for i, session in enumerate(sessions, start=1):
            label = f"  [{i}/{len(sessions)}] {session.session_id} ({session.persona}) ... "
            print(label, end="", flush=True)
            start = time.perf_counter()
            result, was_cached = _judge_or_cache(runner, session)
            print("cached" if was_cached else f"{time.perf_counter() - start:.1f}s")
            results.append((session, result))
    except _RATE_LIMIT_ERRORS:
        print(
            f"\n\nRate limit hit after {len(results)}/{len(sessions)} sessions. Everything "
            "judged so far is cached — re-run `python -m eval.run_eval` to continue (wait for "
            "the daily cap to reset first if you're on the free tier)."
        )
        raise SystemExit(1) from None

    human: dict[str, list[int]] = defaultdict(list)
    model: dict[str, list[int]] = defaultdict(list)
    for session, result in results:
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
