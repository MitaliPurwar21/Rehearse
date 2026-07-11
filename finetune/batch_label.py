"""Bulk labeling via the Anthropic Message Batches API.

Scoring ~1.5k pairs one call at a time is the main cost of the pipeline. The Batches API
runs them asynchronously at half the price, which is what keeps the full run under budget.
This is Claude-specific on purpose: batching is a provider feature, not part of the general
LLMProvider seam.

The batch id is saved to data/label_batch.json so an interrupted poll resumes the same
batch instead of paying to submit a new one. Results already written to labeled.jsonl are
skipped by the caller, so a resumed run is idempotent.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any, cast

from anthropic import Anthropic
from anthropic.types import Message, MessageParam, ToolChoiceToolParam, ToolParam
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from pydantic import ValidationError

from .generate_data import DATA_DIR
from .jobs import JobPosting
from .label_data import prompt_for
from .schemas import FitScore, Pair

_TOOL_NAME = "emit_result"
BATCH_STATE_PATH = DATA_DIR / "label_batch.json"


def _tool_and_choice() -> tuple[ToolParam, ToolChoiceToolParam]:
    # Same trick as ClaudeProvider: one forced tool whose schema is our Pydantic model.
    tool = cast(
        ToolParam,
        {
            "name": _TOOL_NAME,
            "description": "Return the result in the required structured format.",
            "input_schema": cast(Any, FitScore.model_json_schema()),
        },
    )
    choice: ToolChoiceToolParam = {"type": "tool", "name": _TOOL_NAME}
    return tool, choice


def build_requests(
    pairs: list[Pair], jobs_by_id: dict[str, JobPosting], model: str
) -> list[Request]:
    """One batch Request per pair, keyed by pair_id so results can be matched back."""
    tool, choice = _tool_and_choice()
    requests: list[Request] = []
    for pair in pairs:
        job = jobs_by_id[pair.job_id]
        system, user = prompt_for(job, pair.resume_text)
        messages: list[MessageParam] = [{"role": "user", "content": user}]
        params = cast(
            MessageCreateParamsNonStreaming,
            {
                "model": model,
                "max_tokens": 700,
                "temperature": 0.0,
                "system": system,
                "messages": messages,
                "tools": [tool],
                "tool_choice": choice,
            },
        )
        requests.append(Request(custom_id=pair.pair_id, params=params))
    return requests


def fit_from_message(message: Message) -> FitScore:
    """Pull the forced tool call out of a completed batch message and validate it."""
    for block in message.content:
        if block.type == "tool_use" and block.name == _TOOL_NAME:
            return FitScore.model_validate(block.input)
    raise ValueError(f"no {_TOOL_NAME} tool_use block in message")


def _save_batch_id(batch_id: str) -> None:
    BATCH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BATCH_STATE_PATH.write_text(json.dumps({"batch_id": batch_id}), encoding="utf-8")


def _load_batch_id() -> str | None:
    if not BATCH_STATE_PATH.exists():
        return None
    return str(json.loads(BATCH_STATE_PATH.read_text(encoding="utf-8"))["batch_id"])


def _clear_batch_id() -> None:
    BATCH_STATE_PATH.unlink(missing_ok=True)


def run_batch(
    client: Anthropic,
    todo: list[Pair],
    lookup: dict[str, Pair],
    jobs_by_id: dict[str, JobPosting],
    model: str,
    poll_seconds: int = 15,
) -> Iterator[tuple[Pair, FitScore]]:
    """Submit (or resume) a labeling batch and yield (pair, fit) as results come back.

    lookup maps every known pair_id to its Pair, so results from a resumed batch still
    resolve even though todo only holds the not-yet-labeled ones.
    """
    batch_id = _load_batch_id()
    if batch_id is None:
        requests = build_requests(todo, jobs_by_id, model)
        batch = client.messages.batches.create(requests=requests)
        batch_id = batch.id
        _save_batch_id(batch_id)
        print(f"submitted batch {batch_id} ({len(requests)} requests)", flush=True)
    else:
        print(f"resuming batch {batch_id}", flush=True)

    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            break
        print(f"  {batch_id}: {batch.processing_status} {batch.request_counts}", flush=True)
        time.sleep(poll_seconds)

    for item in client.messages.batches.results(batch_id):
        pair = lookup.get(item.custom_id)
        if pair is None:
            continue
        if item.result.type != "succeeded":
            detail = f": {item.result.error}" if item.result.type == "errored" else ""
            print(f"  {item.custom_id}: {item.result.type}{detail} (skipped)", flush=True)
            continue
        try:
            fit = fit_from_message(item.result.message)
        except (ValueError, ValidationError):
            # A malformed or empty tool call: skip this one rather than fail the batch.
            print(f"  {item.custom_id}: unparseable result (skipped)", flush=True)
            continue
        yield pair, fit
    _clear_batch_id()
