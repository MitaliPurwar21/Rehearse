# Golden set label format

The golden set is the hand-labeled ground truth the judge is calibrated against.
One JSONL file, one **session** per line. Each session carries human (gold) scores
per competency per dimension, so we can compute agreement at the dimension level.

```jsonc
{
  "session_id": "ses_0001",
  "split": "validation",            // "calibration" | "validation"
  "job_description": "…full JD text…",
  "competencies": ["RAG systems", "Production debugging", "Communication"],
  "persona": "bullshitter",         // strong | mediocre | terse | bullshitter | off_topic | real
  "turns": [
    {"speaker": "interviewer", "text": "…"},
    {"speaker": "candidate",   "text": "…"}
  ],
  "gold": [
    {
      "competency": "RAG systems",
      "dimension_scores": {"relevance": 4, "depth": 2, "evidence": 2, "communication": 4},
      "competency_score": 3.0        // unweighted mean, rounded to nearest 0.5
    }
  ],
  "label_meta": {
    "annotator": "human_1",
    "pass": 1,                       // 1 or 2 (for the double-labeled subset)
    "adjudicated": true              // true once disagreements resolved to gold
  }
}
```

## Rules
- `split` is fixed once assigned. Calibration rows may seed few-shot exemplars in
  the judge prompt; **only `validation` rows are used for reported metrics.**
- Dimension scores are integers 1–5 against the anchors in `../rubric.yaml`.
- `competency_score` must equal the unweighted mean of its dimension scores
  (rounded to nearest 0.5) — same rule the judge schema enforces.
- The ~20-session double-labeled subset has two rows' worth of labels per session
  (pass 1 and pass 2) retained to compute the human self-consistency ceiling.
