"""Turn a FitScore into a candidate-facing gap report.

The FitScore is recruiter-oriented (it scores the candidate). The gap report flips it to
face the candidate: here's what you match, here's what the role wants that you don't show.
No extra model call: it's a plain reshaping of the score, so it's deterministic and cheap.
"""

from __future__ import annotations

from finetune.schemas import FitScore

from .schemas import GapReport


def _summary(strengths: list[str], gaps: list[str]) -> str:
    if not strengths and not gaps:
        return "Not enough overlap to assess against this role."
    if strengths:
        lead = f"You match on {', '.join(strengths[:3])}."
    else:
        lead = "Few of the role's skills show up."
    if gaps:
        return f"{lead} The role also asks for {', '.join(gaps)}, not clearly shown on your resume."
    return f"{lead} You cover the role's core skills."


def gap_report(fit: FitScore) -> GapReport:
    return GapReport(
        overall_fit=fit.overall_fit,
        strengths=fit.matched_skills,
        gaps=fit.missing_skills,
        summary=_summary(fit.matched_skills, fit.missing_skills),
    )
