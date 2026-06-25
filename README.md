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
│       ├── groq.py       #   Groq impl (free fallback)
│       ├── fake.py       #   deterministic provider for tests (no API key)
│       └── factory.py    #   pick a provider from settings
├── eval/                 # offline evaluation harness
│   ├── rubric.yaml       # 4 universal dimensions × 1–5 anchors + scoring rules
│   ├── judge_prompt.md   # judge system prompt
│   ├── schemas.py        # Pydantic judge output (self-validating)
│   ├── runner.py         # JudgeRunner: transcript → validated SessionEvaluation (+retry)
│   ├── metrics.py        # quadratic-weighted kappa, Spearman, MAE, confusion, bootstrap CI
│   ├── golden.py         # loads the golden set
│   ├── generate.py       # synthesize transcripts to label (live)
│   ├── label.py          # terminal tool to hand-score transcripts
│   ├── run_eval.py       # judge the golden set, report agreement (live)
│   ├── smoke.py          # one-transcript live smoke test
│   └── golden/           # seed.jsonl, unlabeled.jsonl, labeled.jsonl + format spec
├── tests/                # offline unit tests (no network)
└── pyproject.toml
```

Coming in later phases: `services/api/` (FastAPI gateway, ingestion, retrieval),
`apps/web/` (Next.js + LiveKit), `apps/agent/` (LiveKit voice worker), `infra/`
(Docker, GitHub Actions).

## Setup

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # set JUDGE_PROVIDER + the matching API key
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

Agreement report — run the judge over the golden set and compare to the hand labels:

```bash
python -m eval.run_eval
```

Right now the golden set is a tiny seed (5 transcripts) and the numbers are only a
sanity check. The real calibration comes once the full ~50-session golden set is
labeled and judged by Claude.

## Building the golden set

The golden set is interview transcripts with **human** scores — the ground truth the
judge is measured against. Generating a candidate and scoring it are kept separate so
we're never grading a model against itself.

```bash
python -m eval.generate --per-combo 3   # synthesize transcripts -> golden/unlabeled.jsonl
python -m eval.label                     # score them by hand     -> golden/labeled.jsonl
```

`label.py` shows one transcript plus the rubric, takes four 1-5 scores per competency,
hides the candidate type so it can't bias you, and lets you stop and resume anytime.
Once `labeled.jsonl` exists, `run_eval` uses it automatically instead of the seed.
