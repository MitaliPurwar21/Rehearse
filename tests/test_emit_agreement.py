"""The operator's eval Job reads this JSON out of the pod logs, so it has to be one
clean line with the numbers the gate already trusts."""

import json

from eval.emit_agreement import agreement_json


def test_agreement_json_matches_the_frozen_baseline() -> None:
    payload = json.loads(agreement_json())
    # Same frozen judgements the CI gate uses, so the headline number must line up.
    assert payload["n_pairs"] == 408
    assert payload["qwk"] == 0.827
    assert set(payload["dimensions"]) == {"relevance", "depth", "evidence", "communication"}


def test_agreement_json_is_a_single_line() -> None:
    assert "\n" not in agreement_json()
