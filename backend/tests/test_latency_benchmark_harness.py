"""The latency harness is evidence, so its own arithmetic and guards are tested.

A benchmark that silently measures the wrong thing is worse than no benchmark:
the numbers look authoritative and the conclusion drawn from them is wrong.
Two such mistakes were made while building this harness and both are pinned
here -- a Deep run started behind a queue of auto-escalated jobs, and a
validity guard that read cumulative swap rather than the paging rate and so
refused to run on a perfectly idle host.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[2] / "scripts" / "latency_benchmark.py"
SPEC = importlib.util.spec_from_file_location("latency_benchmark", SCRIPT)
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


def test_percentile_interpolates_and_tolerates_empty_input() -> None:
    assert HARNESS.percentile([], 0.95) is None
    assert HARNESS.percentile([100.0], 0.95) == 100.0
    assert HARNESS.percentile([100.0, 200.0, 300.0, 400.0], 0.5) == 250.0


def test_summarise_reports_p50_and_p95_and_a_count() -> None:
    summary = HARNESS.summarise([float(value) for value in range(1, 101)])
    assert summary["count"] == 100
    assert summary["p50"] == pytest.approx(50.5, abs=0.01)
    assert summary["p95"] == pytest.approx(95.05, abs=0.05)
    assert HARNESS.summarise([])["p50"] is None


def test_query_set_is_versioned_and_covers_the_behaviours_under_protection() -> None:
    """A before/after comparison is only valid across one query set.

    The set must keep exercising abstention and a non-citizen role, because
    an optimisation that quietly broke either would otherwise look like a win:
    abstaining more often is faster, and so is ignoring role profiles.
    """
    assert HARNESS.QUERY_SET_VERSION
    ids = [item["id"] for item in HARNESS.QUERY_SET]
    assert len(ids) == len(set(ids)), "query ids must be unique"
    rendered = " ".join(item["query"] for item in HARNESS.QUERY_SET).casefold()
    for expected in ("warrant", "fir", "article 14", "contract", "custody"):
        assert expected in rendered
    assert {item["role"] for item in HARNESS.QUERY_SET} >= {"citizen", "police"}


def test_stage_breakdown_sums_retries_and_accounts_for_every_llm_call() -> None:
    """A retry is a second pass through the same stages, not a different stage.

    Reporting only the last pass hid the cost the retry loop exists to bound.
    """
    metrics = [
        {"stage": "reasoning", "duration_ms": 1000.0, "llm_calls": [
            {"duration_ms": 900.0, "response_prompt_eval_count": 3000, "response_eval_count": 800},
        ]},
        {"stage": "verification", "duration_ms": 500.0, "llm_calls": [
            {"duration_ms": 400.0, "response_prompt_eval_count": 2000, "response_eval_count": 100},
            {"duration_ms": 50.0, "response_prompt_eval_count": 300, "response_eval_count": 20},
        ]},
        {"stage": "reasoning", "retry_index": 1, "duration_ms": 1200.0, "llm_calls": []},
        {"stage": "workflow_total", "duration_ms": 9999.0, "llm_calls": []},
    ]
    breakdown = HARNESS.stage_breakdown(metrics)
    assert breakdown["stages_ms"]["reasoning"] == 2200.0
    assert "workflow_total" not in breakdown["stages_ms"]
    assert breakdown["llm_call_count"] == 3
    assert breakdown["llm_output_tokens"] == 920
    assert breakdown["llm_prompt_tokens"] == 5300


def test_answer_quality_records_what_must_not_regress() -> None:
    body = {
        "answer": "The law requires X. [Source 1]",
        "evidence_strength": "moderate",
        "confidence_score": 0.62,
        "citations": [
            {
                "title": "Bharatiya Nagarik Suraksha Sanhita, 2023",
                "source_type": "statute",
                "section": "35",
                "source_url": "https://example.invalid/bnss",
                "verification_status": "verified",
                "repeal_label": "in_force",
            },
            {
                "title": "Some Judgment",
                "source_type": "judgment",
                "section": None,
                "source_url": None,
                "verification_status": "unverified",
                "repeal_label": "no_longer_in_force",
            },
        ],
        "agent_trace": [
            {"node": "verification", "details": {"score": 0.8, "claims": 5, "unsupported": 1, "unadjudicated": 0}},
        ],
    }
    quality = HARNESS.answer_quality(body)
    assert quality["citation_count"] == 2
    assert quality["distinct_source_titles"] == 2
    assert quality["distinct_source_types"] == 2
    assert quality["citations_with_section"] == 1
    assert quality["verified_citations"] == 1
    assert quality["repeal_labelled_citations"] == 1
    assert quality["verification_score"] == 0.8
    assert quality["verification_unsupported"] == 1
    assert quality["abstained"] is False


def test_an_insufficient_evidence_answer_is_recorded_as_an_abstention() -> None:
    """Abstention is a quality signal in both directions.

    An optimisation that abstains more often gets faster and worse, and one
    that abstains less often may have loosened a safety gate. Neither is
    visible unless the rate is recorded.
    """
    quality = HARNESS.answer_quality(
        {"answer": "Insufficient verified evidence to answer.", "evidence_strength": "insufficient", "citations": []}
    )
    assert quality["abstained"] is True
    assert quality["citation_count"] == 0


def test_the_validity_guard_watches_the_paging_rate_not_cumulative_swap() -> None:
    """macOS never returns swap once allocated.

    An earlier guard refused to measure on an idle host that reported 8 GB of
    cumulative swap from an ingestion hours earlier. What invalidates a run is
    active paging, so the threshold is a rate.
    """
    assert HARNESS.MAX_SWAPOUT_PAGES_PER_SECOND > 0
    assert HARNESS.SWAP_RATE_SAMPLE_SECONDS > 0
    assert 0 < HARNESS.MAX_LOAD_PER_CPU_FOR_VALID_RUN <= 1
    assert not hasattr(HARNESS, "MAX_SWAP_BYTES_FOR_VALID_RUN")


def test_busy_process_markers_name_the_tasks_that_invalidate_a_run() -> None:
    assert "promote_candidates" in HARNESS.BUSY_PROCESS_MARKERS
    assert any("rebuild" in marker for marker in HARNESS.BUSY_PROCESS_MARKERS)
