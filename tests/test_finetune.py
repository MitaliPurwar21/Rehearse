"""Offline tests for the fine-tuning data pipeline. No network, no API key."""

from __future__ import annotations

import json
import random
from typing import TypeVar

import pytest
from pydantic import BaseModel, ValidationError

from finetune.generate_data import generate_pairs
from finetune.jobs import FIT_LEVELS, JOBS
from finetune.label_data import label_pair
from finetune.prepare import split_records, to_row
from finetune.schemas import FitScore, GeneratedResume, LabeledPair, Pair
from rehearse_core.llm.fake import FakeProvider

T = TypeVar("T", bound=BaseModel)

_RESUME = (
    "Jane Doe. Senior engineer with eight years building and shipping production systems. "
    "Experience: led a platform team, built CI/CD, owned reliability. Skills: Python, "
    "Kubernetes, Terraform. Education: BS Computer Science."
)


def _fit(**over: object) -> FitScore:
    base: dict[str, object] = {
        "overall_fit": 80,
        "skills_match": 4,
        "experience_match": 4,
        "seniority_match": 5,
        "matched_skills": ["Python"],
        "missing_skills": ["Go"],
        "rationale": "Strong overlap on the core skills.",
    }
    base.update(over)
    return FitScore.model_validate(base)


def test_fitscore_rejects_out_of_range() -> None:
    with pytest.raises(ValidationError):
        _fit(overall_fit=101)
    with pytest.raises(ValidationError):
        _fit(skills_match=6)


def test_fitscore_rejects_empty_rationale() -> None:
    with pytest.raises(ValidationError):
        _fit(rationale="   ")


def test_fitscore_dedupes_skills_case_insensitively() -> None:
    fit = _fit(matched_skills=["Python", "python", " Python ", "SQL"])
    assert fit.matched_skills == ["Python", "SQL"]


def test_generate_pairs_sample_caps_and_numbers() -> None:
    provider = FakeProvider(GeneratedResume(resume_text=_RESUME))
    pairs = list(
        generate_pairs(
            provider,
            per_combo=99,
            sample=5,
            start_idx=1,
            temperature=0.9,
            rng=random.Random(0),
        )
    )
    assert len(pairs) == 5
    assert [p.pair_id for p in pairs] == [f"pair_{i:04d}" for i in range(1, 6)]
    # Every pair carries a known job and fit level.
    known_jobs = {j["job_id"] for j in JOBS}
    assert all(p.job_id in known_jobs for p in pairs)
    assert all(p.fit_level in FIT_LEVELS for p in pairs)


def test_generate_pairs_skips_bad_model_output() -> None:
    # A provider whose every response fails validation: the run should skip all of them
    # rather than raise, so one flaky response can't kill a long generation job.
    class _EmptyProvider:
        model_id = "empty"

        def structured(
            self,
            *,
            system: str,
            user: str,
            schema: type[T],
            temperature: float = 0.0,
            max_tokens: int = 4096,
        ) -> T:
            return schema.model_validate({})  # missing fields -> ValidationError

    pairs = list(
        generate_pairs(
            _EmptyProvider(),
            per_combo=99,
            sample=3,
            start_idx=1,
            temperature=0.9,
            rng=random.Random(0),
        )
    )
    assert pairs == []


def test_generate_pairs_per_combo_covers_all_combos() -> None:
    provider = FakeProvider(GeneratedResume(resume_text=_RESUME))
    pairs = list(
        generate_pairs(
            provider, per_combo=1, sample=None, start_idx=1, temperature=0.9, rng=random.Random(0)
        )
    )
    assert len(pairs) == len(JOBS) * len(FIT_LEVELS)


def test_label_pair_attaches_fit() -> None:
    provider = FakeProvider(_fit(overall_fit=72))
    pair = Pair(
        pair_id="pair_0001", job_id=JOBS[0]["job_id"], fit_level="strong", resume_text=_RESUME
    )
    labeled = label_pair(provider, JOBS[0], pair)
    assert isinstance(labeled, LabeledPair)
    assert labeled.pair_id == "pair_0001"
    assert labeled.fit.overall_fit == 72


def _labeled_set() -> list[LabeledPair]:
    records = []
    i = 0
    for level in FIT_LEVELS:
        for _ in range(10):
            i += 1
            records.append(
                LabeledPair(
                    pair_id=f"pair_{i:04d}",
                    job_id=JOBS[i % len(JOBS)]["job_id"],
                    fit_level=level,
                    resume_text=_RESUME,
                    fit=_fit(),
                )
            )
    return records


def test_split_is_stratified_deterministic_and_leak_free() -> None:
    records = _labeled_set()
    a = split_records(records, seed=0, val_frac=0.1, test_frac=0.1)
    b = split_records(records, seed=0, val_frac=0.1, test_frac=0.1)

    # Deterministic.
    assert [r.pair_id for r in a["test"]] == [r.pair_id for r in b["test"]]

    # No pair appears in two splits; every pair is placed.
    ids = {s: {r.pair_id for r in a[s]} for s in a}
    assert ids["train"].isdisjoint(ids["val"])
    assert ids["train"].isdisjoint(ids["test"])
    assert ids["val"].isdisjoint(ids["test"])
    assert sum(len(v) for v in ids.values()) == len(records)

    # Each fit level is represented in test (stratified), 1 per level at 10% of 10.
    test_levels = {r.fit_level for r in a["test"]}
    assert test_levels == set(FIT_LEVELS)


def test_build_requests_keys_by_pair_id_and_carries_prompt() -> None:
    from finetune.batch_label import build_requests
    from finetune.label_data import _JOBS_BY_ID

    pairs = [
        Pair(
            pair_id="pair_0001", job_id=JOBS[0]["job_id"], fit_level="strong", resume_text=_RESUME
        ),
        Pair(
            pair_id="pair_0002", job_id=JOBS[1]["job_id"], fit_level="partial", resume_text=_RESUME
        ),
    ]
    reqs = build_requests(pairs, _JOBS_BY_ID, "claude-sonnet-4-6")
    assert [r["custom_id"] for r in reqs] == ["pair_0001", "pair_0002"]
    params = reqs[0]["params"]
    assert params["model"] == "claude-sonnet-4-6"
    assert params["tool_choice"] == {"type": "tool", "name": "emit_result"}
    # the resume text rides along in the user message
    content = list(params["messages"])[0]["content"]
    assert isinstance(content, str) and _RESUME in content


def test_fit_from_message_extracts_tool_call() -> None:
    from anthropic.types import Message, ToolUseBlock

    from finetune.batch_label import fit_from_message

    block = ToolUseBlock(
        type="tool_use", id="t1", name="emit_result", input=_fit().model_dump()
    )
    message = Message.model_construct(content=[block])
    got = fit_from_message(message)
    assert got.overall_fit == 80


def test_fit_from_message_raises_without_tool_call() -> None:
    from anthropic.types import Message, TextBlock

    from finetune.batch_label import fit_from_message

    message = Message.model_construct(content=[TextBlock(type="text", text="no tool here")])
    with pytest.raises(ValueError):
        fit_from_message(message)


def test_extract_fit_parses_clean_and_embedded() -> None:
    from finetune.eval_screener import extract_fit

    clean = _fit().model_dump_json()
    assert extract_fit(clean) is not None
    embedded = "Here is the score: " + clean + " done."
    got = extract_fit(embedded)
    assert got is not None and got.overall_fit == 80
    assert extract_fit("no json here at all") is None


def test_evaluate_counts_parse_failures_and_metrics() -> None:
    from finetune.eval_screener import evaluate

    test: list[dict[str, object]] = [
        {"pair_id": "pair_0001", "fit": _fit(overall_fit=80, skills_match=4).model_dump()},
        {"pair_id": "pair_0002", "fit": _fit(overall_fit=40, skills_match=2).model_dump()},
        {"pair_id": "pair_0003", "fit": _fit(overall_fit=60, skills_match=3).model_dump()},
    ]
    preds = {
        "pair_0001": _fit(overall_fit=82, skills_match=4).model_dump_json(),
        "pair_0002": _fit(overall_fit=38, skills_match=2).model_dump_json(),
        "pair_0003": "garbage, not json",  # unparseable -> excluded from the agreement
    }
    report = evaluate(test, preds)
    assert report.n_test == 3
    assert report.n_predicted == 3
    assert report.n_parsed == 2
    assert set(report.subdims) == {"skills_match", "experience_match", "seniority_match"}
    assert report.overall_mae >= 0.0


def test_evaluate_handles_zero_parsed() -> None:
    # The raw-baseline case: nothing parses. It must report cleanly, not crash.
    from finetune.eval_screener import evaluate

    test: list[dict[str, object]] = [
        {"pair_id": "pair_0001", "fit": _fit().model_dump()},
        {"pair_id": "pair_0002", "fit": _fit().model_dump()},
    ]
    preds = {"pair_0001": "**overall_fit**: 90 (markdown, not json)", "pair_0002": "prose"}
    report = evaluate(test, preds)
    assert report.n_parsed == 0
    assert report.subdims == {}


def test_to_row_roundtrips_completion() -> None:
    record = _labeled_set()[0]
    row = to_row(record, "train")
    assert row["split"] == "train"
    assert isinstance(row["prompt"], str) and record.resume_text in row["prompt"]
    # completion is valid JSON that parses back into a FitScore.
    parsed = FitScore.model_validate(json.loads(row["completion"]))  # type: ignore[arg-type]
    assert parsed.overall_fit == record.fit.overall_fit
