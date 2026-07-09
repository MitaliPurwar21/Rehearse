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

I ran two probes on a 12-transcript sample of the golden set, judged by the calibrated
Claude judge at temperature 0 — the exact setting the product ships.

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

## What I'd do next

- **Self-consistency (median of N runs)** would shrink the wander further, especially on
  communication. The stability numbers are the justification for adding it — and the
  before/after would be measurable.
- **Self-enhancement check:** does the Claude judge favor Claude-written answers over
  ones written by a different model? That's the next probe to add to `eval/audit.py`.

## Honest limits

- The audit runs on a 12-transcript subset (to keep it cheap); it's representative but
  small, same as the golden set.
- Calibration is still against a **single** labeler on **technical** roles — the main
  limitation, spelled out in the README. The audit tests the judge's behavior, not
  whether my labels are the "right" ground truth.

## Reproduce

```bash
python -m eval.audit              # both probes on a 12-transcript sample
python -m eval.audit --n 20 --runs 7   # bigger sample, more repeats
```

It's live (calls the judge) but cached and resumable — a rate limit or a network blip
mid-run costs nothing, since every judged transcript is written to disk before the next.
Results print as the tables above and land in `eval/audit_report.json`.
