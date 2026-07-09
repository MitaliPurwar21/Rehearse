# Evaluating the judge

Most "AI app" projects never check their AI. Rehearse leans the other way: the judge
that scores interviews is treated as something to validate, not just ship. There are two
questions I care about, and they're different.

1. **Does the judge agree with a human?** That's calibration — measured against my
   hand-labeled golden set. The headline number (quadratic-weighted κ **0.83**) and the
   per-dimension breakdown live in the [README](../README.md#results).
2. **Can I actually trust it?** A judge can hit a good agreement number and still be
   fooled by a confident, empty answer, or wander so much run-to-run that the score is
   half luck. Agreement doesn't catch either. So I stress-tested the judge directly.

This doc is about the second question. Everything here comes from `python -m eval.audit`.

## Why quadratic-weighted kappa

The scores are ordinal (1–5) and I want to punish a 5-vs-1 miss far more than a 5-vs-4
one. Plain accuracy treats those the same; Pearson pretends the labels are continuous.
Quadratic-weighted Cohen's kappa does exactly what I want and also corrects for
agreement you'd get by chance, which matters on a skewed 1–5 distribution. I report a
bootstrap CI alongside it because the golden set is small and a point estimate alone
would oversell it.

## Auditing the judge

Three probes. The first two run on a 12-transcript sample of the golden set, judged by
the calibrated Claude judge at temperature 0 — the exact setting the product ships. The
third pits the Claude judge against Groq to check for self-preference.

### 1. Verbosity: does padding fool it?

The worry with any LLM judge is that it rewards *fluency* over *substance* — a candidate
who talks a lot and says little. To test it, I took real answers and wrapped every
candidate turn in fixed, content-free filler ("that's a really great question, something
I care a lot about…") that adds length and zero information, then re-judged and compared
against the original.

If the judge graded how an answer *sounds*, the scores would go up. Here's what actually
moved (mean change = padded score minus original, over 24 competency scores per
dimension):

| dimension | mean change | up / down / same |
|---|---|---|
| relevance | −0.33 | 0 / 8 / 16 |
| **depth** | **−0.04** | 0 / 1 / 23 |
| **evidence** | **+0.00** | 1 / 1 / 22 |
| communication | **−1.42** | 0 / 24 / 0 |

Reading it:

- **Depth and evidence don't move.** Padding an answer with waffle buys nothing on the
  two dimensions that are supposed to track what was actually said. This is the
  anti-"bullshitter" property the rubric was written for, and it holds up when I try to
  break it.
- **Communication drops hard** (every single case). The judge notices a rambly, padded
  answer communicates *worse* — which is correct, not a bug. Communication is meant to be
  sensitive to exactly this.
- **Relevance dips slightly** because filler dilutes how on-topic the turn reads.

So the judge grades substance, not length. That's the result I wanted.

### 2. Stability: how much does it wander?

Even at temperature 0 an LLM isn't perfectly deterministic. I judged the same transcript
5 times and measured how far each score spread (standard deviation across the repeats;
0 means identical every time).

| dimension | mean std | max std | identical every run |
|---|---|---|---|
| relevance | 0.06 | 0.49 | 88% |
| depth | 0.10 | 0.49 | 79% |
| evidence | 0.15 | 0.49 | 67% |
| communication | 0.18 | 0.49 | 58% |

Reading it:

- **The wander is small and always bounded.** `max std` is 0.49 across the board, which
  is the spread of a single ±1 split over five runs — no score ever swung further than
  one point. The judge is close to deterministic, not erratic.
- **Concrete dimensions are steadier than holistic ones.** Relevance (is this on-topic?)
  is unanimous 88% of the time; communication (a more subjective read) only 58%. The
  gradient is exactly what you'd expect — the fuzzier the judgment, the more it moves.
- **The noise is small next to the signal.** The judge's own run-to-run wander (≤0.18)
  is well under half the human–judge gap (MAE 0.51). So most of the disagreement behind
  the 0.83 is real difference of opinion, not the model being inconsistent with itself.

### 3. Self-preference: does the judge favour its own writing?

LLM judges have been shown to score text their own model produced higher than an
outside judge would — self-enhancement bias. If mine did that, some of the 0.83 would
be the model admiring its own reflection rather than measuring quality.

I tested it with a round-robin (`python -m eval.self_pref`). Same fixed interview
questions; Claude and Groq each answer them as a strong candidate; then *both* models
judge *both* sets of answers. If Claude's answers are simply better, both judges should
agree by roughly the same margin. Self-preference is the **extra** margin a judge gives
its own family — a difference-in-differences. Mean score per cell, 16 answers each:

| | author = Claude | author = Groq |
|---|---|---|
| **judge = Claude** | 4.59 | 3.59 |
| **judge = Groq** | 4.75 | 4.42 |

- lift (Claude judge) = **+1.00**, lift (Groq judge) = **+0.33**
- self-preference (difference-in-differences) = **+0.67**

Reading it honestly:

- **Both judges rank Claude's answers above Groq's**, so Claude genuinely writes the
  better answers here — even the rival judge agrees. That part is real quality, not bias.
- **The Claude judge's margin is three times the independent judge's.** At face value
  that's self-preference: the Claude judge rewards its own family about two-thirds of a
  point more than an outsider does.
- **But the reference judge is weak, which muddies it.** Look at the Groq judge's row —
  4.75 and 4.42, everything bunched high. It barely separates good answers from bad,
  while the Claude judge clearly does (4.59 vs 3.59). So the +0.67 mixes two things:
  genuine self-preference, and the Claude judge just being a better discriminator than
  the Groq reference. You can't cleanly split those with a weak reference.

So I read this as a **suggestive but confounded** signal, not a clean measurement — a
flag worth chasing with a stronger reference judge, not a final number. It's also why I
don't let the shipped Claude judge be the *only* scorer in a setting where Claude may
have written what's being scored.

## What I'd do next

- **A stronger, independent third judge** (a GPT-4-class model) to disambiguate the
  self-preference number above. With only a weak reference I can't separate real
  self-preference from the Claude judge simply discriminating better.
- **Self-consistency (median of N runs)** would shrink the wander further, especially on
  communication. The stability numbers are the justification for adding it — and the
  before/after would be measurable.

## Honest limits

- The probes run on small samples to keep them cheap (12 transcripts for verbosity and
  stability; 2 jobs × 4 answers for self-preference). Representative, but small — same as
  the golden set.
- The self-preference number uses Groq as the only independent reference, and Groq is a
  weak discriminator, so +0.67 is a flag to investigate, not a verdict (see that section).
- Calibration is still against a **single** labeler on **technical** roles — the main
  limitation, spelled out in the README. The audit tests the judge's behavior, not
  whether my labels are the "right" ground truth.

## Reproduce

```bash
python -m eval.audit                   # verbosity + stability on a 12-transcript sample
python -m eval.audit --n 20 --runs 7   # bigger sample, more repeats
python -m eval.self_pref --per-job 4   # self-preference round-robin (needs both API keys)
```

It's live (calls the judge) but cached and resumable — a rate limit or a network blip
mid-run costs nothing, since every judged transcript is written to disk before the next.
Results print as the tables above and land in `eval/audit_report.json`.
