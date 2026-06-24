# Rehearse

An AI voice interview coach. Paste a job description → it extracts the role's
competencies → conducts a **voice** mock interview grounded in that JD → scores you
against a rubric with a **calibrated LLM-as-judge** (evidence quotes + feedback) →
persists every session so you can track progress over time.

The part I care most about is the **evaluation harness**: a rubric + LLM-as-judge
calibrated against a hand-labeled golden set, with the agreement actually measured
(quadratic-weighted Cohen's κ, Spearman ρ) and a prompt-regression gate in CI so the
grader can't drift unnoticed.

> Status: early build. I'm building the evaluation harness first because it's the
> hardest part to fake and the most worth getting right. Full roadmap in `docs/` (soon).

## Repo layout

```
rehearse/
├── rehearse_core/        # shared infra imported by every service
│   ├── config.py         # env-driven settings (pydantic-settings)
│   └── llm/              # swappable LLM provider interface
│       ├── base.py       #   LLMProvider protocol (structured output)
│       ├── claude.py     #   Claude impl via tool-use
│       └── fake.py       #   deterministic provider for tests (no API key)
├── eval/                 # offline evaluation harness
│   ├── rubric.yaml       # 4 universal dimensions × 1–5 anchors + scoring rules
│   ├── judge_prompt.md   # judge system prompt
│   ├── schemas.py        # Pydantic judge output (self-validating)
│   ├── runner.py         # JudgeRunner: transcript → validated SessionEvaluation
│   ├── smoke.py          # real-API smoke test (needs ANTHROPIC_API_KEY)
│   └── golden/           # hand-labeled golden set + format spec
├── tests/                # offline unit tests (no network)
└── pyproject.toml
```

Coming in later phases: `services/api/` (FastAPI gateway, ingestion, retrieval),
`apps/web/` (Next.js + LiveKit), `apps/agent/` (LiveKit voice worker), `infra/`
(Docker, GitHub Actions).

## Setup

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # fill in ANTHROPIC_API_KEY for the live smoke test
```

## Test

```bash
pytest          # offline unit tests — no API key, no cost
ruff check .
mypy .
```

Optional live check — judges a built-in sample transcript end to end:

```bash
# Free path (Groq), for wiring checks only — not for judge calibration:
#   set JUDGE_PROVIDER=groq and GROQ_API_KEY in .env
# Strong path (Claude), what the judge is actually calibrated on:
#   set JUDGE_PROVIDER=claude and ANTHROPIC_API_KEY in .env
python -m eval.smoke
```
