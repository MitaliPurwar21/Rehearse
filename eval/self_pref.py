"""Self-preference probe: does the Claude judge favour Claude-written answers?

A known failure mode of LLM-as-judge is self-enhancement — a model scores text its
own family produced higher than an independent judge would. If my judge did that, the
0.83 would be partly the model liking its own reflection, not real quality.

The design controls for quality with a round-robin. Same fixed interviewer questions;
two models (Claude, Groq) each play a strong candidate and answer them; then BOTH
models judge BOTH sets of answers. If Claude answers are simply better, both judges
agree they're better by the same margin. Self-preference is the *extra* boost a judge
gives its own family beyond what the other judge sees — a difference-in-differences:

    lift(judge)      = mean score it gives Claude answers - mean it gives Groq answers
    self_preference  = lift(Claude judge) - lift(Groq judge)

Near 0 means no self-preference. Positive means the judges reward their own family.

Needs both an ANTHROPIC_API_KEY and a GROQ_API_KEY. It's live, but every generation
and judgement is cached, so a rate limit or running out of credit mid-run costs
nothing — fix it and re-run to resume. Run by hand:

    python -m eval.self_pref                # 2 answers per job, both judges
    python -m eval.self_pref --per-job 4
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from pydantic import BaseModel

from eval.audit import _RESUMABLE_API_ERRORS
from eval.generate import JOBS, Job
from eval.runner import JudgeRunner, Transcript
from eval.schemas import SessionEvaluation
from rehearse_core.config import get_settings
from rehearse_core.llm.base import LLMProvider

_CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "selfpref"
_REPORT_PATH = Path(__file__).resolve().parent / "selfpref_report.json"

_GEN_SYSTEM = (
    "You are a strong job candidate in a live technical interview. Answer each question "
    "concretely and specifically in the first person: give a real example, name the "
    "approach and the tradeoffs, and include a metric or outcome. One focused paragraph "
    "per question, no filler."
)


class AnswerSet(BaseModel):
    """A candidate's answers, one per interviewer question, in order."""

    answers: list[str]


def questions_for(job: Job) -> list[str]:
    """One fixed question per competency. Identical for both authors so the only thing
    that differs between the two answer sets is who wrote them."""
    return [
        f"Tell me about your experience with {c}. Walk me through a specific example."
        for c in job["competencies"]
    ]


def assemble_transcript(job: Job, questions: list[str], answers: list[str]) -> Transcript:
    """Interleave the fixed questions with one author's answers into a transcript."""
    turns: list[tuple[str, str]] = []
    for q, a in zip(questions, answers, strict=False):  # pair up to the shorter of the two
        turns.append(("interviewer", q))
        turns.append(("candidate", a))
    return Transcript(
        job_description=job["job_description"],
        competencies=job["competencies"],
        turns=turns,
    )


# --- caching -----------------------------------------------------------------


def _safe(name: str) -> str:
    return name.replace("/", "-")


def _gen_cache_path(job_idx: int, author: str, variant: int) -> Path:
    return _CACHE_DIR / f"gen__job{job_idx}__{_safe(author)}__v{variant}.json"


def _judge_cache_path(
    job_idx: int, author: str, variant: int, judge: str, prompt_hash: str
) -> Path:
    name = (
        f"judge__job{job_idx}__auth-{_safe(author)}__v{variant}"
        f"__by-{_safe(judge)}__{prompt_hash[:12]}"
    )
    return _CACHE_DIR / f"{name}.json"


def _author_answers(
    provider: LLMProvider, job: Job, questions: list[str], job_idx: int, variant: int
) -> list[str]:
    path = _gen_cache_path(job_idx, provider.model_id, variant)
    if path.exists():
        return AnswerSet.model_validate_json(path.read_text(encoding="utf-8")).answers
    result = provider.structured(
        system=_GEN_SYSTEM,
        user=(
            f"Role: {job['role']}\nJob description: {job['job_description']}\n\n"
            "Answer each interviewer question:\n"
            + "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
        ),
        schema=AnswerSet,
        temperature=0.7,  # a little spread so the variants aren't identical
        max_tokens=1500,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(), encoding="utf-8")
    return result.answers


def _judge_transcript(
    runner: JudgeRunner, transcript: Transcript, job_idx: int, author: str, variant: int
) -> SessionEvaluation:
    path = _judge_cache_path(job_idx, author, variant, runner.provider.model_id, runner.prompt_hash)
    if path.exists():
        return SessionEvaluation.model_validate_json(path.read_text(encoding="utf-8"))
    result = runner.judge(transcript)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(), encoding="utf-8")
    return result


# --- the experiment ----------------------------------------------------------


def mean_competency_score(ev: SessionEvaluation) -> list[float]:
    return [c.competency_score for c in ev.competency_evaluations]


def self_preference(matrix: dict[tuple[str, str], float]) -> dict[str, float]:
    """Turn the 2x2 mean-score matrix into lifts and the difference-in-differences.

    matrix maps (judge, author) -> mean score, with keys "claude" and "groq".
    """
    s = matrix
    lift_claude_judge = s[("claude", "claude")] - s[("claude", "groq")]
    lift_groq_judge = s[("groq", "claude")] - s[("groq", "groq")]
    return {
        "lift_claude_judge": round(lift_claude_judge, 3),
        "lift_groq_judge": round(lift_groq_judge, 3),
        "self_preference": round(lift_claude_judge - lift_groq_judge, 3),
    }


def run_self_pref(
    authors: dict[str, LLMProvider],
    judges: dict[str, JudgeRunner],
    *,
    per_job: int,
    max_jobs: int | None = None,
) -> dict[str, object]:
    # (judge, author) -> every competency score gathered under that cell
    cells: dict[tuple[str, str], list[float]] = {
        (j, a): [] for j in judges for a in authors
    }
    # Slicing keeps the original job indexes (0, 1, ...), so cached results line up.
    for job_idx, job in enumerate(JOBS[:max_jobs] if max_jobs else JOBS):
        questions = questions_for(job)
        for author_name, author in authors.items():
            for variant in range(per_job):
                tag = f"job{job_idx} {author_name} v{variant}"
                print(f"  answering [{tag}] ...", flush=True)
                answers = _author_answers(author, job, questions, job_idx, variant)
                transcript = assemble_transcript(job, questions, answers)
                for judge_name, runner in judges.items():
                    print(f"    judged by {judge_name} ...", flush=True)
                    ev = _judge_transcript(runner, transcript, job_idx, author_name, variant)
                    cells[(judge_name, author_name)].extend(mean_competency_score(ev))

    matrix = {key: statistics.fmean(v) for key, v in cells.items() if v}
    report: dict[str, object] = {
        "n_per_cell": {f"{j}|{a}": len(cells[(j, a)]) for j, a in cells},
        "mean_scores": {f"{j}|{a}": round(matrix[(j, a)], 3) for j, a in matrix},
    }
    if len(matrix) == 4:  # both judges and both authors present
        report["preference"] = self_preference(matrix)
    return report


def _print_report(report: dict[str, object]) -> None:
    scores = report["mean_scores"]
    assert isinstance(scores, dict)
    print("\nSELF-PREFERENCE — mean score in each (judge, author) cell")
    print(f"  {'':<16}{'author=claude':>16}{'author=groq':>14}")
    for judge in ("claude", "groq"):
        cc = scores.get(f"{judge}|claude")
        cg = scores.get(f"{judge}|groq")
        cc_s = f"{cc:.2f}" if cc is not None else "-"
        cg_s = f"{cg:.2f}" if cg is not None else "-"
        print(f"  judge={judge:<10}{cc_s:>16}{cg_s:>14}")
    pref = report.get("preference")
    if isinstance(pref, dict):
        print(
            f"\n  lift(Claude judge) = {pref['lift_claude_judge']:+.3f}   "
            f"lift(Groq judge) = {pref['lift_groq_judge']:+.3f}"
        )
        print(f"  self-preference (difference-in-differences) = {pref['self_preference']:+.3f}")
        print("  (near 0 = no self-preference; positive = judges favour their own family)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Self-preference probe (Claude vs Groq).")
    parser.add_argument("--per-job", type=int, default=2, help="answer variants per author per job")
    parser.add_argument(
        "--max-jobs", type=int, default=None, help="use only the first N jobs (default: all)"
    )
    args = parser.parse_args()

    settings = get_settings()
    from rehearse_core.llm.claude import ClaudeProvider
    from rehearse_core.llm.groq import GroqProvider

    ak = settings.anthropic_api_key
    gk = settings.groq_api_key
    if not ak or not gk:
        raise SystemExit(
            "This probe needs BOTH keys (it runs Claude and Groq against each other). "
            "Set ANTHROPIC_API_KEY and GROQ_API_KEY in .env."
        )
    authors: dict[str, LLMProvider] = {
        "claude": ClaudeProvider(api_key=ak, model_id=settings.judge_model),
        "groq": GroqProvider(api_key=gk, model_id=settings.groq_model),
    }
    judges = {name: JudgeRunner(p) for name, p in authors.items()}

    njobs = min(args.max_jobs, len(JOBS)) if args.max_jobs else len(JOBS)
    print(f"Self-preference: {njobs} jobs x {args.per_job} answers x 2 authors x 2 judges")
    try:
        report = run_self_pref(authors, judges, per_job=args.per_job, max_jobs=args.max_jobs)
    except _RESUMABLE_API_ERRORS as err:
        print(
            f"\n\nThe API stopped us: {err}\nEverything generated and judged so far is "
            "cached — sort it out (add credits / wait) and re-run to resume."
        )
        raise SystemExit(1) from None

    _print_report(report)
    _REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote {_REPORT_PATH.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
