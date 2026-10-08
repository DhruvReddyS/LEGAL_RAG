"""The comparison applies one definition to both runs.

A metric definition that changes between a before run and an after run
produces a difference that is not a difference. Two definitions in this
project drifted while the code looked identical, and the abstention rule in
this harness was itself wrong once -- it read `evidence_strength` and so
counted a published 247-word answer as a refusal. The comparison therefore
recomputes from stored records rather than reading either run's summary, and
refuses to compare runs recorded against different query sets.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "latency_compare.py"
SPEC = importlib.util.spec_from_file_location("latency_compare", SCRIPT)
assert SPEC and SPEC.loader
COMPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPARE)


def _report(label: str, *, records, query_set_version="latency-v1"):
    return {
        "label": label,
        "generated_at": "2026-10-08T00:00:00+00:00",
        "query_set_version": query_set_version,
        "environment": {
            "git_commit": "0123456789abcdef",
            "qdrant_collection": "global_legal_corpus_v4",
            "qdrant_points": 49684,
            "load_average": [1.0, 1.0, 1.0],
            "swapout_pages_per_second": 0.0,
            "initial_job_queue_depth": 0,
            "health_ready": {"inference": {"embedding": "mps"}},
        },
        "records": records,
    }


def _record(mode="deep", query_id="q01", wall_ms=90_000.0, **overrides):
    record = {
        "mode": mode,
        "query_id": query_id,
        "repeat": 0,
        "wall_ms": wall_ms,
        "time_to_first_useful_output_ms": wall_ms,
        "time_to_first_final_output_ms": wall_ms,
        "citation_count": 4,
        "distinct_source_titles": 4,
        "distinct_source_types": 2,
        "citations_with_section": 3,
        "citations_with_url": 4,
        "answer_words": 300,
        "verification_score": 0.7,
        "verification_claims": 8,
        "verification_unsupported": 1,
        "verification_unadjudicated": 0,
        "evidence_strength": "moderate",
        "answer": "A police officer may arrest without a warrant. [Source 1]",
        "llm_call_count": 3,
        "llm_prompt_tokens": 6000,
        "llm_output_tokens": 900,
        "stages_ms": {"reasoning": 50_000.0, "verification": 30_000.0},
        "timings_ms": {"workflow_total_ms": wall_ms},
    }
    record.update(overrides)
    return record


def test_a_mismatched_query_set_is_called_out_rather_than_averaged() -> None:
    rendered = COMPARE.render(
        _report("before", records=[_record()]),
        _report("after", records=[_record()], query_set_version="latency-v2"),
    )
    assert "not comparable" in rendered


def test_the_abstention_rate_is_recomputed_from_the_stored_answers() -> None:
    """Not read from either run's summary.

    The baseline here was recorded while the harness still mislabelled a
    thin-but-published answer as a refusal. Recomputing is what makes that
    baseline usable instead of discarded.
    """
    refusal = _record(
        query_id="q07",
        answer="I could not find enough reliable support in the indexed legal corpus for this answer.",
        evidence_strength="insufficient",
        citation_count=0,
    )
    published_but_thin = _record(query_id="q02", evidence_strength="insufficient")
    rendered = COMPARE.render(
        _report("before", records=[refusal, published_but_thin]),
        _report("after", records=[refusal, published_but_thin]),
    )
    assert "| Abstention rate | 0.5 | 0.5 | +0.00 (+0.0%) |" in rendered
    assert "| Published but graded insufficient | 0.5 | 0.5 |" in rendered


def test_an_improvement_is_reported_with_its_percentage() -> None:
    rendered = COMPARE.render(
        _report("before", records=[_record(wall_ms=100_000.0)]),
        _report("after", records=[_record(wall_ms=75_000.0)]),
    )
    assert "-25,000.00 (-25.0%)" in rendered


def test_a_first_useful_output_that_improves_alone_is_distinguishable() -> None:
    """Progressive output must not be able to masquerade as a faster answer."""
    rendered = COMPARE.render(
        _report("before", records=[_record(wall_ms=90_000.0)]),
        _report(
            "after",
            records=[
                _record(
                    wall_ms=90_000.0,
                    time_to_first_useful_output_ms=7_000.0,
                    time_to_first_final_output_ms=90_000.0,
                )
            ],
        ),
    )
    assert "Time to first useful output p50 | 90,000 | 7,000" in rendered
    assert "Time to first final output p50 | 90,000 | 90,000 | +0.00" in rendered
    assert "End-to-end p50 | 90,000 | 90,000 | +0.00" in rendered


def test_per_query_rows_make_a_single_query_regression_visible() -> None:
    """An aggregate can hide one question getting worse while others improve."""
    rendered = COMPARE.render(
        _report("before", records=[_record(query_id="q01", wall_ms=60_000.0), _record(query_id="q04", wall_ms=160_000.0)]),
        _report("after", records=[_record(query_id="q01", wall_ms=40_000.0), _record(query_id="q04", wall_ms=200_000.0)]),
    )
    assert "| q01 | 60.00 | 40.00 " in rendered
    assert "| q04 | 160.00 | 200.00 " in rendered
