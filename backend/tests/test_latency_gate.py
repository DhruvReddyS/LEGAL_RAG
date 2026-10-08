"""The gate that stops a latency change being paid for with evidence.

The correctness suite has been green through every retrieval regression this
project has had. It cannot see a serialisation added to a hot path, a second
model request on a hot loop, or an optimisation that got faster by publishing
fewer citations. This gate can, and these tests pin the two decisions in it
that are easy to get wrong.

The first is what it refuses to gate. Deep latency is output tokens divided by
the host's decode rate, and that rate is not a property of this repository:
the same reasoning prompt producing the same 597 tokens took 42.5 s on a hot
laptop and 26.4 s on a cool one. A gate on Deep end-to-end would fail on a
warm afternoon and pass a real regression on a cold morning.

The second is the direction of each quality check. Fewer citations, more
abstentions and more unsupported claims are all failures, and all three are
things an optimisation can produce while looking like a win.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[2] / "scripts" / "check_latency_gate.py"
SPEC = importlib.util.spec_from_file_location("check_latency_gate", SCRIPT)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def _deep(**overrides):
    record = {
        "mode": "deep",
        "query_id": "q01",
        "wall_ms": 65_000.0,
        "time_to_first_useful_output_ms": 600.0,
        "citation_count": 4,
        "verification_unsupported": 5,
        "answer": "The Sanhita permits arrest without a warrant in the stated cases. [Source 1]",
        "evidence_strength": "moderate",
        "llm_decode_tokens_per_second": 14.4,
        "stages_ms": {
            "role_context": 0.06,
            "query_understanding": 0.2,
            "retrieval": 86.0,
            "retrieval_enrichment": 16.0,
            "reasoning": 52_399.0,
            "verification": 10_100.0,
            "response_generation": 2.0,
        },
        "timings_ms": {},
    }
    record.update(overrides)
    return record


def _fast(**overrides):
    record = {
        "mode": "fast",
        "query_id": "q01",
        "wall_ms": 180.0,
        "time_to_first_useful_output_ms": 180.0,
        "citation_count": 4,
        "answer": "Four passages. [Source 1]",
        "evidence_strength": "strong",
        "stages_ms": {},
        "timings_ms": {"embedding_ms": 120.0},
    }
    record.update(overrides)
    return record


def _report(records, label="shipped"):
    return {
        "label": label,
        "query_set_version": "latency-v1",
        "environment": {"git_commit": "abc", "validity_warnings": []},
        "records": records,
    }


def test_the_overhead_measure_excludes_the_stages_the_model_owns() -> None:
    """Reasoning and verification are the model's cost, not the code's.

    Including them would make the gate a thermometer.
    """
    overhead = GATE.non_model_overhead_ms(_deep())
    # retrieval + enrichment + response generation + role context. Query
    # understanding is excluded too: it is skipped for a self-contained
    # question and costs a 6.5-second model call when it is not, so its
    # presence in the sum would depend on the phrasing of the question
    # rather than on anything the code did.
    assert overhead == pytest.approx(86.0 + 16.0 + 2.0 + 0.06, abs=0.01)
    assert "query_understanding" in GATE.MODEL_STAGES
    assert overhead < 200, "the orchestration is a tenth of a second; the model is a minute"


def test_deep_end_to_end_is_recorded_but_never_gated() -> None:
    measured = GATE.measure(_report([_deep()]))
    assert "context_deep_end_to_end_p50_ms" in measured
    assert "context_deep_end_to_end_p95_ms" in measured
    assert "context_deep_decode_tokens_per_second_p50" in measured
    for key in GATE.LATENCY_KEYS:
        assert not key.startswith("context_")
    assert all("end_to_end" not in key for key in GATE.LATENCY_KEYS)


def test_a_host_that_decodes_half_as_fast_still_passes() -> None:
    """The regression this gate must not invent.

    Same code, hot laptop: every model stage doubles. Nothing in this
    repository changed, so the build must stay green.
    """
    contract = {"query_set_version": "latency-v1", "measured": GATE.measure(_report([_deep()]))}
    slow_host = _deep(
        wall_ms=130_000.0,
        llm_decode_tokens_per_second=7.2,
        stages_ms={**_deep()["stages_ms"], "reasoning": 104_798.0, "verification": 20_200.0},
    )
    assert GATE.check(GATE.measure(_report([slow_host])), contract) == []


def test_a_serialisation_added_to_the_orchestration_fails() -> None:
    """The regression this gate exists for.

    An await per candidate, or a per-citation database round trip, lands in
    exactly these stages and is invisible next to a 52-second model call.
    """
    contract = {"query_set_version": "latency-v1", "measured": GATE.measure(_report([_deep()]))}
    regressed = _deep(stages_ms={**_deep()["stages_ms"], "retrieval": 4_000.0})
    failures = GATE.check(GATE.measure(_report([regressed])), contract)
    assert any("deep_non_model_overhead_p95_ms" in failure for failure in failures)


def test_buying_speed_with_citations_fails() -> None:
    contract = {"query_set_version": "latency-v1", "measured": GATE.measure(_report([_deep()]))}
    failures = GATE.check(GATE.measure(_report([_deep(citation_count=2)])), contract)
    assert any("speed was bought with evidence" in failure for failure in failures)


def test_buying_speed_by_abstaining_more_fails() -> None:
    contract = {
        "query_set_version": "latency-v1",
        "measured": GATE.measure(_report([_deep(), _deep(query_id="q02")])),
    }
    refusing = _deep(
        query_id="q02",
        answer="I could not find enough reliable support in the indexed legal corpus for this answer.",
        citation_count=4,
    )
    failures = GATE.check(GATE.measure(_report([_deep(), refusing])), contract)
    assert any("refusing more often is not an optimisation" in failure for failure in failures)


def test_more_unsupported_claims_fails() -> None:
    contract = {"query_set_version": "latency-v1", "measured": GATE.measure(_report([_deep()]))}
    failures = GATE.check(GATE.measure(_report([_deep(verification_unsupported=9)])), contract)
    assert any("deep_unsupported_claims_per_query" in failure for failure in failures)


def test_a_slower_first_useful_output_fails() -> None:
    """Deep's readable progress is a property worth defending.

    It was 64.7 s before retrieval started publishing its sources, and a
    change that quietly moved the event back behind verification would
    restore that without any other number moving.
    """
    contract = {"query_set_version": "latency-v1", "measured": GATE.measure(_report([_deep()]))}
    regressed = _deep(time_to_first_useful_output_ms=65_000.0)
    failures = GATE.check(GATE.measure(_report([regressed])), contract)
    assert any("deep_first_useful_output_p95_ms" in failure for failure in failures)


def test_a_different_query_set_is_refused_rather_than_compared() -> None:
    contract = {"query_set_version": "latency-v0", "measured": GATE.measure(_report([_deep()]))}
    failures = GATE.check(GATE.measure(_report([_deep()])), contract)
    assert len(failures) == 1
    assert "not comparable" in failures[0]


def test_the_fast_lane_is_gated_on_its_own_p95() -> None:
    """Fast runs no model, so its end-to-end number is the code's own."""
    contract = {"query_set_version": "latency-v1", "measured": GATE.measure(_report([_fast()]))}
    assert GATE.check(GATE.measure(_report([_fast(wall_ms=250.0)])), contract) == []
    failures = GATE.check(GATE.measure(_report([_fast(wall_ms=5_000.0)])), contract)
    assert any("fast_p95_ms" in failure for failure in failures)


def test_a_run_with_validity_warnings_cannot_set_or_pass_the_gate(tmp_path) -> None:
    """A measurement taken on a loaded host is not evidence of anything."""
    report = _report([_deep()])
    report["environment"]["validity_warnings"] = ["host is paging at 900 swapouts/s"]
    result = tmp_path / "run.json"
    result.write_text(json.dumps(report), encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({"query_set_version": "latency-v1", "measured": {}}), encoding="utf-8")
    import sys

    argv = sys.argv
    sys.argv = ["check_latency_gate.py", "--result", str(result), "--contract", str(contract)]
    try:
        assert GATE.main() == 2
    finally:
        sys.argv = argv
