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


def test_stage_breakdown_reads_the_keys_the_pipeline_actually_writes() -> None:
    """A retry is a second pass through the same stages, not a different one.

    Reporting only the last pass hid the cost the retry loop exists to bound.

    The key names matter more than they look. An earlier version read
    `response_prompt_eval_count` and `duration_ms`, which `_success_metric`
    does not write, so an entire baseline recorded zero prompt tokens and
    zero LLM time -- and a zero there reads as "free" rather than "not
    measured". These are the real names.
    """
    metrics = [
        {"stage": "reasoning", "duration_ms": 1000.0, "llm_calls": [
            {
                "wall_ms": 900.0,
                "prompt_eval_count": 3000,
                "response_eval_count": 800,
                "ollama_prompt_eval_duration_ms": 300.0,
                "ollama_eval_duration_ms": 560.0,
                "ollama_load_duration_ms": 10.0,
                "generation_queue_wait_ms": 1.0,
                "time_to_first_response_token_ms": 320.0,
            },
        ]},
        {"stage": "verification", "duration_ms": 500.0, "llm_calls": [
            {
                "wall_ms": 400.0,
                "prompt_eval_count": 2000,
                "response_eval_count": 100,
                "ollama_prompt_eval_duration_ms": 200.0,
                "ollama_eval_duration_ms": 180.0,
            },
            {
                "wall_ms": 50.0,
                "prompt_eval_count": 300,
                "response_eval_count": 20,
                "ollama_prompt_eval_duration_ms": 20.0,
                "ollama_eval_duration_ms": 25.0,
            },
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
    assert breakdown["llm_total_ms"] == 1350.0
    # Prefill and decode respond to completely different changes, so a single
    # LLM total cannot tell you which one an optimisation moved.
    assert breakdown["llm_prefill_ms"] == 520.0
    assert breakdown["llm_decode_ms"] == 765.0
    assert breakdown["llm_model_load_ms"] == 10.0
    assert breakdown["llm_queue_wait_ms"] == 1.0
    assert breakdown["llm_first_token_ms_max"] == 320.0
    assert breakdown["llm_decode_tokens_per_second"] == round(920 / 0.765, 2)


def test_a_breakdown_with_no_llm_calls_reports_no_decode_rate() -> None:
    """Fast runs no model. A rate of zero would be a false measurement."""
    breakdown = HARNESS.stage_breakdown([{"stage": "retrieval", "duration_ms": 40.0}])
    assert breakdown["llm_call_count"] == 0
    assert breakdown["llm_decode_tokens_per_second"] is None


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


def test_abstention_is_the_refusal_text_not_the_strength_label() -> None:
    """These are different facts and conflating them corrupted the rate.

    Deep publishes a 247-word answer with four citations and still labels
    `evidence_strength` "insufficient" when the published score falls under
    0.5. Reading that label as a refusal reported 29% abstention on a query
    set where the pipeline refused one question in seven.
    """
    published_but_thin = {
        "answer": "A police officer may arrest without a warrant where the Sanhita so provides. [Source 1]",
        "evidence_strength": "insufficient",
        "citations": [{"title": "BNSS", "source_type": "act"}],
    }
    assert HARNESS.abstained(published_but_thin) is False
    quality = HARNESS.answer_quality(published_but_thin)
    assert quality["abstained"] is False
    assert quality["published_but_graded_insufficient"] is True

    refusal = {
        "answer": "I could not find enough reliable support in the indexed legal corpus for this answer.",
        "evidence_strength": "insufficient",
        "citations": [],
    }
    assert HARNESS.abstained(refusal) is True
    assert HARNESS.answer_quality(refusal)["published_but_graded_insufficient"] is False


def test_an_empty_answer_counts_as_an_abstention() -> None:
    assert HARNESS.abstained({"answer": "", "citations": []}) is True
    assert HARNESS.abstained({"citations": []}) is True
