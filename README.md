# Rehearse

An AI voice interview coach. Paste a job description → it extracts the role's
competencies → conducts a **voice** mock interview grounded in that JD → scores you
against a rubric with a **calibrated LLM-as-judge** (evidence quotes + feedback) →
persists every session so you can track progress over time.

The part I care most about is the **evaluation harness**: a rubric + LLM-as-judge
calibrated against a hand-labeled golden set, with the agreement actually measured
(quadratic-weighted Cohen's κ, Spearman ρ) and a prompt-regression gate in CI so the
grader can't drift unnoticed.

> Status: the evaluation harness is built and calibrated. The rest of the product
> (JD ingestion, voice interview, database, web UI, deploy) is upcoming. I built the
> harness first because it's the hardest part to fake and the most worth getting right.

## Results

The judge (Claude Sonnet) was calibrated against a hand-labeled golden set of **51
technical interviews / 408 individual scores** (ML engineer, data scientist, backend).

| | Agreement (judge vs. human) |
|---|---|
| **Overall (quadratic-weighted κ)** | **0.83** (95% CI 0.78–0.86) |
| Spearman ρ | 0.85 |
| Mean abs. error | 0.51 (on a 1–5 scale) |
| Exact match | 59% |

Per dimension: depth **0.90**, evidence 0.82, communication 0.73, relevance 0.69.
~92% of disagreements are off by a single point; the main systematic gap is that the
human labeler scores slightly more leniently than the judge at the top of the scale.

Honest scope: a **single** human labeler, validated on **technical** roles only (where
those labels are credible). The rubric and harness are role-agnostic; extending
validation to other domains needs a domain-expert labeler.

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
│   ├── agreement.py      # pair gold vs judge scores + summarize (provider-free)
│   ├── golden.py         # loads the golden set
│   ├── generate.py       # synthesize transcripts to label (live)
│   ├── label.py          # terminal tool to hand-score transcripts
│   ├── run_eval.py       # judge the golden set, report agreement (live, cached)
│   ├── freeze_baseline.py# lock in the current result as the CI baseline
│   ├── check_regression.py # CI gate: fail if agreement drops (offline)
│   ├── baseline.json     # the frozen agreement numbers the gate checks
│   ├── smoke.py          # one-transcript live smoke test
│   └── golden/           # labeled.jsonl, unlabeled.jsonl, judgements.jsonl, seed.jsonl
├── ingestion/            # job description -> competencies
│   ├── schemas.py        #   JobProfile / Competency (validated)
│   ├── extract.py        #   extract_competencies(jd, provider)
│   ├── cli.py            #   demo: print competencies for a JD
│   └── sample_jd.txt     #   an example to try it on
├── services/api/         # FastAPI gateway + persistence
│   ├── main.py           #   routes: POST /jobs, GET /jobs, GET /jobs/{id}
│   ├── models.py         #   SQLAlchemy tables (Job, Competency)
│   ├── db.py             #   engine + session (SQLite by default)
│   ├── schemas.py        #   request/response shapes
│   └── deps.py           #   injectable DB + provider (overridden in tests)
├── .github/workflows/    # CI: ruff, mypy, pytest, eval regression gate
├── tests/                # offline unit tests (no network)
└── pyproject.toml
```

Coming in later phases: `apps/web/` (Next.js + LiveKit), `apps/agent/` (LiveKit voice
worker), a FastAPI gateway, a database, and deployment.

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

Judge results are cached, so re-runs are instant and a rate limit mid-run doesn't lose
progress — it resumes where it stopped.

## Ingestion: job description → competencies

Paste (or pipe) a job description and the model extracts the competencies an interview
should assess — schema-constrained, grounded in the JD, no generic filler.

```bash
python -m ingestion.cli ingestion/sample_jd.txt
cat my_jd.txt | python -m ingestion.cli
```

## API

A FastAPI service stores jobs and their extracted competencies (SQLite by default).

```bash
uvicorn services.api.main:app --reload      # http://127.0.0.1:8000/docs for the API docs

# create a job from a JD (runs ingestion, persists the result):
curl -X POST localhost:8000/jobs -H 'Content-Type: application/json' \
  -d '{"job_description": "Senior ML Engineer building RAG systems..."}'

curl localhost:8000/jobs            # list stored jobs
curl localhost:8000/jobs/1          # fetch one
```

Interview and scoring endpoints come in later phases; the data model is built to hang
sessions and evaluations off a job.

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

## Regression gate (CI)

A grader is only useful if it doesn't silently get worse. So the agreement is frozen
as a baseline and checked on every change:

```bash
python -m eval.freeze_baseline    # re-judge the golden set, lock in baseline.json (live)
python -m eval.check_regression   # recompute agreement from frozen outputs, compare (offline)
```

`check_regression` runs in CI (no API key) and fails the build if overall κ drops more
than 0.05 below baseline, or any dimension's error rises more than 0.30 — catching
scoring/metric bugs (like a competency-matching change that quietly drops data). A
*prompt* change is handled deliberately: re-run `freeze_baseline` and the new numbers
show up in the git diff for review.
