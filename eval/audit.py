"""Audit the judge, not just measure it once.

run_eval answers "how well does the judge agree with my labels?". This answers a
different, harder question: "where does the judge break, and can I trust it?" Two
probes so far:

  * verbosity — pad an answer with content-free waffle and re-judge it. If the
    scores go up, the judge is rewarding fluency over substance. On the depth and
    evidence dimensions especially they shouldn't move: nothing was actually said.
  * stability — judge the same transcript several times and see how far the scores
    wander. Tells you how much of the headline number is signal and how much is the
    model being moody, and whether it's safe to ship at temperature 0.

Live (it calls the model), but cached and resumable exactly like run_eval, so a
rate limit or a network blip costs you nothing on a re-run. Run by hand:

    python -m eval.audit                    # both probes, small default sample
    python -m eval.audit --n 15 --runs 5    # bigger sample, more repeats
    python -m eval.audit --only stability --temp 0.7   # sensitivity at temp 0.7

Writes a JSON summary to eval/audit_report.json for the write-up.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import TypedDict

import eval.run_eval as run_eval
from eval.agreement import golden_path
from eval.golden import DIMENSIONS, GoldenSession, load_golden
from eval.runner import JudgeRunner, Transcript
from eval.schemas import SessionEvaluation

_CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "audit"
_REPORT_PATH = Path(__file__).resolve().parent / "audit_report.json"

# Errors that mean "the API said no" — rate limits, out of credits, overloaded. None
# of these are our bug, and every judged transcript is already on disk, so we bail out
# cleanly and tell you to re-run once it's sorted rather than dumping a traceback.
_RESUMABLE_API_ERRORS: tuple[type[BaseException], ...] = ()
try:
    from anthropic import APIStatusError as _AnthropicAPIError

    _RESUMABLE_API_ERRORS += (_AnthropicAPIError,)
except ImportError:  # pragma: no cover
    pass
try:
    from groq import APIStatusError as _GroqAPIError

    _RESUMABLE_API_ERRORS += (_GroqAPIError,)
except ImportError:  # pragma: no cover
    pass

# Content-free padding. The point is words with no substance: if wrapping an answer
# in this pushes the scores up, the judge is grading how it sounds, not what's in it.
# Fixed text, not model-generated, so it can't sneak in any real content and so the
# experiment reproduces byte-for-byte.
_FILLER_PREFIX = (
    "Yeah, so that's a really great question, and honestly it's something I care a lot "
    "about. Let me think about how best to put this. I suppose where I'd start is just to "
    "say that this whole area really matters to me and I've thought about it quite a bit. "
)
_FILLER_SUFFIX = (
    " So yeah, that's basically my overall take on it, if that makes sense. There's a lot "
    "more I could get into and I could easily keep going, but I think that covers the main "
    "gist of where I'm coming from on this one."
)


def pad_answer(text: str) -> str:
    """Wrap an answer in filler that adds length but no content."""
    return f"{_FILLER_PREFIX}{text}{_FILLER_SUFFIX}"


def padded_transcript(session: GoldenSession) -> Transcript:
    """Same transcript, but every candidate turn is padded with filler.

    The interviewer's turns are left alone — only the answers get the waffle.
    """
    turns = [
        (t["speaker"], pad_answer(t["text"]) if t["speaker"] == "candidate" else t["text"])
        for t in session.turns
    ]
    return Transcript(
        job_description=session.job_description,
        competencies=session.competencies,
        turns=turns,
    )


def _dim_scores(ev: SessionEvaluation) -> dict[str, dict[str, int]]:
    """competency (casefolded) -> {dimension: score}, matching pair_scores' keying."""
    out: dict[str, dict[str, int]] = {}
    for c in ev.competency_evaluations:
        out[c.competency.strip().casefold()] = {d.dimension: d.score for d in c.dimension_scores}
    return out


# --- caching -----------------------------------------------------------------
# Keyed by everything that could change the answer: which transcript, which variant
# (original vs padded), which repeat, the temperature, the model, and the prompt.


def _cache_path(
    session_id: str, variant: str, run_idx: int, temperature: float, model_id: str, prompt_hash: str
) -> Path:
    safe_model = model_id.replace("/", "-")
    name = f"{session_id}__{variant}__r{run_idx}__t{temperature}__{safe_model}__{prompt_hash[:12]}"
    return _CACHE_DIR / f"{name}.json"


def _judge_cached(
    runner: JudgeRunner, transcript: Transcript, session_id: str, variant: str, run_idx: int
) -> SessionEvaluation:
    path = _cache_path(
        session_id,
        variant,
        run_idx,
        runner.temperature,
        runner.provider.model_id,
        runner.prompt_hash,
    )
    if path.exists():
        return SessionEvaluation.model_validate_json(path.read_text(encoding="utf-8"))
    result = runner.judge(transcript)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(), encoding="utf-8")
    return result


def _canonical(runner: JudgeRunner, session: GoldenSession) -> SessionEvaluation:
    """The plain judgement of the untouched transcript.

    Reuses run_eval's cache, so if you've already run the golden set at this
    temperature/prompt these come back free.
    """
    result, _ = run_eval._judge_or_cache(runner, session)
    return result


# --- verbosity probe ---------------------------------------------------------


class DimShift(TypedDict):
    n: int
    mean_delta: float  # padded minus original; want ~0 for depth/evidence
    mean_abs_delta: float
    increased: int
    decreased: int
    unchanged: int


class VerbosityReport(TypedDict):
    n_sessions: int
    dimensions: dict[str, DimShift]


def _shift(deltas: list[int]) -> DimShift:
    return {
        "n": len(deltas),
        "mean_delta": round(statistics.fmean(deltas), 3) if deltas else 0.0,
        "mean_abs_delta": round(statistics.fmean([abs(d) for d in deltas]), 3) if deltas else 0.0,
        "increased": sum(1 for d in deltas if d > 0),
        "decreased": sum(1 for d in deltas if d < 0),
        "unchanged": sum(1 for d in deltas if d == 0),
    }


def run_verbosity(runner: JudgeRunner, sessions: list[GoldenSession]) -> VerbosityReport:
    deltas: dict[str, list[int]] = defaultdict(list)
    for i, session in enumerate(sessions, start=1):
        print(f"  verbosity [{i}/{len(sessions)}] {session.session_id} ...", flush=True)
        base = _dim_scores(_canonical(runner, session))
        padded = _dim_scores(
            _judge_cached(runner, padded_transcript(session), session.session_id, "padded", 0)
        )
        for comp, base_dims in base.items():
            padded_dims = padded.get(comp)
            if padded_dims is None:
                continue
            for dim in DIMENSIONS:
                if dim in base_dims and dim in padded_dims:
                    deltas[dim].append(padded_dims[dim] - base_dims[dim])
    return {
        "n_sessions": len(sessions),
        "dimensions": {dim: _shift(deltas[dim]) for dim in DIMENSIONS if deltas[dim]},
    }


# --- stability probe ---------------------------------------------------------


class DimStability(TypedDict):
    n_cells: int  # (session, competency) pairs measured on this dimension
    mean_std: float  # average spread of a score across repeats
    max_std: float
    unanimous_share: float  # fraction of cells where every repeat gave the same score


class StabilityReport(TypedDict):
    n_sessions: int
    runs: int
    temperature: float
    dimensions: dict[str, DimStability]


def _stability(cells: list[list[int]]) -> DimStability:
    # Each cell is one (session, competency, dimension)'s scores across the repeats.
    stds = [statistics.pstdev(c) for c in cells]
    unanimous = sum(1 for c in cells if len(set(c)) == 1)
    return {
        "n_cells": len(cells),
        "mean_std": round(statistics.fmean(stds), 3) if stds else 0.0,
        "max_std": round(max(stds), 3) if stds else 0.0,
        "unanimous_share": round(unanimous / len(cells), 3) if cells else 0.0,
    }


def run_stability(
    runner: JudgeRunner, sessions: list[GoldenSession], *, runs: int, canonical_temp: float
) -> StabilityReport:
    # dim -> list of cells; a cell is one competency's scores across the repeats.
    cells: dict[str, list[list[int]]] = defaultdict(list)
    for i, session in enumerate(sessions, start=1):
        print(f"  stability [{i}/{len(sessions)}] {session.session_id} x{runs} ...", flush=True)
        # (competency, dimension) -> one score per run
        gathered: dict[tuple[str, str], list[int]] = defaultdict(list)
        for run_idx in range(runs):
            # The first repeat at the shipping temperature is just the canonical run,
            # so reuse it instead of paying for an identical call.
            if run_idx == 0 and runner.temperature == canonical_temp:
                ev = _canonical(runner, session)
            else:
                transcript = session.to_transcript()
                ev = _judge_cached(runner, transcript, session.session_id, "repeat", run_idx)
            for comp, dims in _dim_scores(ev).items():
                for dim, score in dims.items():
                    gathered[(comp, dim)].append(score)
        for (_comp, dim), scores in gathered.items():
            # Only count a cell the judge scored on every repeat, so std is over equal n.
            if dim in DIMENSIONS and len(scores) == runs:
                cells[dim].append(scores)
    return {
        "n_sessions": len(sessions),
        "runs": runs,
        "temperature": runner.temperature,
        "dimensions": {dim: _stability(cells[dim]) for dim in DIMENSIONS if cells[dim]},
    }


# --- reporting ---------------------------------------------------------------


def _print_verbosity(r: VerbosityReport) -> None:
    print("\nVERBOSITY — padding answers with content-free filler")
    print("(mean_delta = judge's score on the padded answer minus the original;")
    print(" for depth and evidence it should sit near 0 — no real content was added)\n")
    print(f"  {'dimension':<14}{'n':>4}{'mean_delta':>12}{'mean_abs':>10}{'up/down/same':>16}")
    for dim in DIMENSIONS:
        s = r["dimensions"].get(dim)
        if s is None:
            continue
        ud = f"{s['increased']}/{s['decreased']}/{s['unchanged']}"
        print(
            f"  {dim:<14}{s['n']:>4}{s['mean_delta']:>+12.3f}"
            f"{s['mean_abs_delta']:>10.3f}{ud:>16}"
        )


def _print_stability(r: StabilityReport) -> None:
    print(f"\nSTABILITY — same transcript judged {r['runs']}x at temperature {r['temperature']}")
    print("(mean_std = average wander of a single score across the repeats; 0 = identical)\n")
    print(f"  {'dimension':<14}{'cells':>6}{'mean_std':>10}{'max_std':>9}{'unanimous':>11}")
    for dim in DIMENSIONS:
        s = r["dimensions"].get(dim)
        if s is None:
            continue
        print(
            f"  {dim:<14}{s['n_cells']:>6}{s['mean_std']:>10.3f}"
            f"{s['max_std']:>9.3f}{s['unanimous_share']:>10.0%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Stress-test the judge (verbosity + stability).")
    parser.add_argument("--n", type=int, default=12, help="how many transcripts to use")
    parser.add_argument("--runs", type=int, default=5, help="repeats per transcript for stability")
    parser.add_argument(
        "--temp", type=float, default=None, help="temperature for the stability repeats"
    )
    parser.add_argument("--only", choices=["verbosity", "stability"], help="run just one probe")
    args = parser.parse_args()

    sessions = load_golden(golden_path())[: args.n]
    if not sessions:
        raise SystemExit("No golden sessions found.")

    base_runner = run_eval.build_runner()  # shipping temperature (0 by default)
    print(f"Auditing {len(sessions)} transcripts with {base_runner.provider.model_id}")
    print(
        f"(temperature {base_runner.temperature}, "
        f"prompt {base_runner.prompt_hash[:12]}, cache reused)"
    )

    report: dict[str, object] = {
        "model_id": base_runner.provider.model_id,
        "prompt_hash": base_runner.prompt_hash,
        "n_sessions": len(sessions),
    }

    def save() -> None:
        _REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    try:
        if args.only != "stability":
            verbosity = run_verbosity(base_runner, sessions)
            _print_verbosity(verbosity)
            report["verbosity"] = verbosity
            save()  # persist now so a later stability failure can't lose this

        if args.only != "verbosity":
            # A different temperature needs its own runner (temperature is fixed at build).
            if args.temp is None or args.temp == base_runner.temperature:
                stab_runner = base_runner
            else:
                stab_runner = JudgeRunner(base_runner.provider, temperature=args.temp)
            stability = run_stability(
                stab_runner, sessions, runs=args.runs, canonical_temp=base_runner.temperature
            )
            _print_stability(stability)
            report["stability"] = stability
            save()
    except _RESUMABLE_API_ERRORS as err:
        print(
            f"\n\nThe API stopped us: {err}\nEverything judged so far is cached, so once "
            "that's sorted (add credits / wait out the rate limit) just re-run the same "
            "command — it picks up where it left off."
        )
        raise SystemExit(1) from None

    print(f"\nWrote {_REPORT_PATH.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
