"""Extract competencies from a job description and print them.

    python -m ingestion.cli path/to/jd.txt
    cat jd.txt | python -m ingestion.cli       # or pipe it in

Uses the provider from your .env (JUDGE_PROVIDER). Calls the model, so it costs a little.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ingestion.extract import extract_competencies
from rehearse_core.config import get_settings
from rehearse_core.llm.factory import build_provider


def main() -> None:
    if len(sys.argv) > 1:
        jd = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        jd = sys.stdin.read()
    if not jd.strip():
        raise SystemExit("No job description given. Pass a file path or pipe text in.")

    provider = build_provider(get_settings())
    profile = extract_competencies(jd, provider)

    header = profile.role_title
    # The model sometimes folds seniority into the title too; don't double it up.
    if profile.seniority and not header.lower().startswith(profile.seniority.lower()):
        header = f"{profile.seniority} {header}"
    print(f"\nRole: {header}")
    print(f"\n{len(profile.competencies)} competencies:")
    for c in profile.competencies:
        print(f"  - {c.name}: {c.description}")


if __name__ == "__main__":
    main()
