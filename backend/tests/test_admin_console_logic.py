"""The console's pure logic: reading evidence, comparing runs, aggregating numbers."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from qdrant_client import AsyncQdrantClient, models

from app.core.config import settings
from app.services import quarantine
from app.services.admin_corpus import currency_flag, document_queues
from app.services.admin_evidence import EvaluationRun, compare_runs, list_evaluation_runs
from app.services.admin_quality import (
    AnswerSignal,
    aggregate_days,
    percentile,
    total_latency_ms,
    unsupported_from_metrics,
)
from app.services.admin_release import (
    COLLECTION_RE,
    LABEL_RE,
    read_gate_document,
    read_gate_evidence,
    status_from_output,
)
from app.services.retrieval import RetrievalFilters
from app.ingestion.metadata import CanonicalDocument

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Currency payload gate passed.", "passed"),
        ("quality gate FAILED:\n  citation_accuracy_at_5", "failed"),
        ("answer gate passed", "passed"),
        ("\nno provision became unreachable", "passed"),
        ("\nREGRESSION: no longer reachable -- BNSS 187", "failed"),
        ("12 passed, 0 failed, 0 blocked", "passed"),
        ("11 passed, 1 failed, 0 blocked", "failed"),
        ("10 passed, 0 failed, 2 blocked", "incomplete"),
        ("something already holds port 8000; stop it", "skipped"),
        ("the evaluation itself failed; see answer-eval.log", "failed"),
        ("Inference Embeddings: 100%", "incomplete"),
        # A pass line does not outrank a failure earlier in the same output.
        ("UNSUPPORTED CLAIMS -- this is a rule\nanswer gate passed", "failed"),
    ],
)
def test_each_gates_output_reads_as_what_it_means(text: str, expected: str) -> None:
    assert status_from_output(text) == expected


def test_the_real_v5_evidence_reads_as_the_handoff_describes(monkeypatch) -> None:
    monkeypatch.setattr(settings, "gate_evidence_root", str(REPO / "docs/evidence/gates"))
    evidence = read_gate_evidence("v5-cutover")
    status = {gate["key"]: gate["status"] for gate in evidence["gates"]}
    assert status["payload"] == "passed"
    assert status["retrieval"] == "failed"
    # Stopped at 8 of 61: an evaluation log and no verdict. Not "not run".
    assert status["answers"] == "incomplete"
    assert status["latency"] == "not_run"
    assert evidence["all_passed"] is False
    assert "HANDOFF.md" in evidence["documents"]


def test_a_summary_is_final_over_the_per_gate_files(tmp_path, monkeypatch) -> None:
    label = tmp_path / "rel"
    label.mkdir()
    (label / "payload.txt").write_text("Currency payload gate passed.")
    (label / "SUMMARY.md").write_text(
        "| Gate | Result |\n|---|---|\n| payload | **FAILED** |\n| latency | skipped |\n"
        "| provisions (exit 1) | **FAILED** |\n"
    )
    monkeypatch.setattr(settings, "gate_evidence_root", str(tmp_path))
    status = {gate["key"]: gate["status"] for gate in read_gate_evidence("rel")["gates"]}
    assert status["payload"] == "failed"
    assert status["latency"] == "skipped"
    assert status["provisions"] == "failed"


@pytest.mark.parametrize("label", ["../secrets", "a/b", "", ".hidden", "UPPER"])
def test_a_label_cannot_leave_the_evidence_directory(tmp_path, monkeypatch, label: str) -> None:
    monkeypatch.setattr(settings, "gate_evidence_root", str(tmp_path))
    with pytest.raises(HTTPException) as refused:
        read_gate_evidence(label)
    assert refused.value.status_code in {404, 422}


@pytest.mark.parametrize("name", ["../other/secret.txt", "backend.log", "script.sh", "missing.md"])
def test_only_text_evidence_in_the_label_can_be_opened(tmp_path, monkeypatch, name: str) -> None:
    (tmp_path / "rel").mkdir()
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "secret.txt").write_text("not this")
    (tmp_path / "rel" / "backend.log").write_text("not this")
    (tmp_path / "rel" / "script.sh").write_text("not this")
    monkeypatch.setattr(settings, "gate_evidence_root", str(tmp_path))
    with pytest.raises(HTTPException) as refused:
        read_gate_document("rel", name)
    assert refused.value.status_code == 404


def test_names_that_reach_a_shell_are_narrow() -> None:
    assert LABEL_RE.fullmatch("v5-cutover")
    assert COLLECTION_RE.fullmatch("global_legal_corpus_v5")
    for bad in ["v5; rm -rf /", "$(id)", "a b", "--flag"]:
        assert not LABEL_RE.fullmatch(bad)
    for bad in ["police_case_data", "global_legal_corpus; id", "other"]:
        assert not COLLECTION_RE.fullmatch(bad)


# ------------------------------------------------------------ stored runs


def test_every_recorded_evaluation_is_readable_and_carries_no_rows() -> None:
    runs = list_evaluation_runs()
    assert {run.kind for run in runs} == {"answers", "retrieval"}
    assert any(run.collection == "global_legal_corpus_v5" for run in runs)
    dumped = json.dumps([run.summary() for run in runs])
    assert '"answer"' not in dumped and '"rows"' not in dumped


def _run(run_id: str, **overrides) -> EvaluationRun:
    base = {
        "id": run_id,
        "kind": "answers",
        "generated_at": "2026-09-01T00:00:00+00:00",
        "collection": "global_legal_corpus_v4",
        "golden_set": "golden_set_v3.json",
        "generation_model": "m",
        "embedding_model": "e",
        "prompt_versions": {"reasoning": "aaa", "verification": "bbb"},
        "metrics": {"abstention_correct": 0.8, "latency_p50_s": 100.0, "items": 61.0},
    }
    return EvaluationRun(**{**base, **overrides})


def test_a_comparison_knows_which_direction_is_better() -> None:
    result = compare_runs(
        _run("a"),
        _run("b", metrics={"abstention_correct": 0.9, "latency_p50_s": 120.0, "items": 70.0}),
    )
    rows = {row["metric"]: row for row in result["metrics"]}
    assert rows["abstention_correct"]["better"] == "b"
    assert rows["latency_p50_s"]["better"] == "a"
    assert rows["items"]["better"] is None
    assert rows["abstention_correct"]["delta"] == pytest.approx(0.1)


def test_a_comparison_flags_what_makes_it_unfair_and_which_prompts_moved() -> None:
    result = compare_runs(
        _run("a"),
        _run(
            "b",
            golden_set="golden_set_v4.json",
            collection="global_legal_corpus_v5",
            prompt_versions={"reasoning": "ccc", "verification": "bbb"},
        ),
    )
    assert any("golden sets" in warning for warning in result["warnings"])
    assert any("corpora" in warning for warning in result["warnings"])
    changed = {row["name"]: row["changed"] for row in result["prompts"]}
    assert changed == {"reasoning": True, "verification": False}


def test_identical_conditions_produce_no_warning() -> None:
    assert compare_runs(_run("a"), _run("b"))["warnings"] == []


# -------------------------------------------------------------- telemetry


def test_percentile_uses_nearest_rank_and_admits_no_data() -> None:
    assert percentile([], 0.5) is None
    assert percentile([10.0], 0.95) == 10.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.0
    assert percentile(list(map(float, range(1, 101))), 0.95) == 95.0


def test_no_verification_is_not_the_same_as_zero_unsupported_claims() -> None:
    assert unsupported_from_metrics([{"stage": "retrieval", "outputs": {}}]) is None
    assert unsupported_from_metrics(None) is None
    assert (
        unsupported_from_metrics(
            [
                {"stage": "verification", "outputs": {"unsupported_claim_count": 3}},
                {"stage": "verification", "outputs": {"unsupported_claim_count": 0}},
            ]
        )
        == 0
    )


def test_latency_reads_the_outermost_timing_available() -> None:
    assert total_latency_ms({"workflow_total_ms": 900, "retrieval_ms": 10}) == 900
    assert total_latency_ms({"retrieval_ms": 10}) is None
    assert total_latency_ms(None) is None


def test_days_aggregate_without_inventing_values() -> None:
    day = date(2026, 11, 1)
    other = date(2026, 11, 2)
    rows = aggregate_days(
        [
            AnswerSignal(day, True, None, 100.0),
            AnswerSignal(day, False, 2, 300.0),
            AnswerSignal(day, False, 0, None),
        ],
        {day: (2, 4)},
        {other: (1, 2)},
    )
    first, second = rows
    assert first["answers"] == 3
    assert first["abstention_rate"] == pytest.approx(0.333)
    assert first["citation_coverage"] == 0.5
    assert first["unsupported_claims"] == 2
    assert first["verified_answers"] == 2
    assert first["latency_p50_ms"] == 100.0
    assert second["abstention_rate"] is None
    assert second["citation_coverage"] is None
    assert second["unsupported_claims"] is None
    assert second["feedback_down"] == 1


# ----------------------------------------------------------------- corpus


def _document(**overrides) -> CanonicalDocument:
    base = {
        "document_id": "d",
        "canonical_document_id": "c",
        "source_id": "s",
        "title": "An Act",
        "original_filename": "a.pdf",
        "local_path": "a.pdf",
        "source_type": "act",
        "category": "primary_law/bns",
        "current_status": "current",
        "sha256": "0" * 64,
        "file_size": 1,
        "page_count": 1,
        "verified_official": True,
        "quality_status": "verified",
    }
    return CanonicalDocument(**{**base, **overrides})


@pytest.mark.parametrize(
    "overrides, flag",
    [
        ({"current_status": "current"}, "current"),
        ({"current_status": "current/verify"}, "unverified"),
        ({"current_status": "repealed"}, "repealed_or_superseded"),
        ({"superseded_by": "x"}, "repealed_or_superseded"),
        ({"currency_note": "commencement not located"}, "warned"),
    ],
)
def test_a_document_is_never_flagged_current_unless_the_corpus_says_so(overrides, flag) -> None:
    assert currency_flag(_document(**overrides)) == flag


def test_the_repeal_table_decides_not_the_manifest_status() -> None:
    """The manifest calls the IPC "current/verify". A browser saying so would be false."""
    ipc = _document(act_name="Indian Penal Code, 1860", title="Indian Penal Code", current_status="current/verify")
    assert currency_flag(ipc) == "repealed_or_superseded"
    assert "currency" not in document_queues(ipc)


def test_work_lists_come_from_what_the_manifest_records() -> None:
    assert document_queues(_document()) == []
    assert document_queues(_document(ocr_required=True)) == ["ocr"]
    assert document_queues(_document(verified_official=False)) == ["verification"]
    assert document_queues(_document(quality_status="needs_review")) == ["verification"]
    assert document_queues(_document(current_status="current/verify")) == ["currency"]


# ------------------------------------------------------------- quarantine


@pytest.fixture
def withheld():
    quarantine.replace_active(frozenset({"bad-doc"}))
    yield
    quarantine.replace_active(frozenset())


def _must_not_keys(query_filter) -> list[str]:
    return [condition.key for condition in (query_filter.must_not or [])]


def test_nothing_quarantined_adds_nothing_to_the_query() -> None:
    assert RetrievalFilters(corpus_tiers=["gold"]).to_qdrant().must_not is None


def test_a_quarantined_document_is_excluded_from_every_global_query(withheld) -> None:
    query_filter = RetrievalFilters(corpus_tiers=["gold", "extended"]).to_qdrant()
    assert _must_not_keys(query_filter) == ["canonical_document_id"]
    assert query_filter.must_not[0].match.any == ["bad-doc"]


def test_a_case_target_is_not_touched(withheld) -> None:
    query_filter = RetrievalFilters(corpus_tiers=[], case_ids=["case-1"]).to_qdrant()
    assert _must_not_keys(query_filter) == []
    assert query_filter.must[0].key == "case_id"


def test_the_exclusion_keeps_the_other_exclusions(withheld) -> None:
    query_filter = RetrievalFilters(exclude_superseded=True).to_qdrant()
    assert set(_must_not_keys(query_filter)) == {"is_superseded", "canonical_document_id"}


@pytest.mark.asyncio
async def test_the_filter_really_removes_the_document_from_a_vector_store(withheld) -> None:
    """Against real Qdrant, because a filter that compiles can still match nothing."""
    import os
    import uuid

    url = os.environ.get("QDRANT_URL")
    if not url or "56333" not in url:
        pytest.skip("needs the throwaway Qdrant")
    name = f"test_quarantine_{uuid.uuid4().hex}"
    client = AsyncQdrantClient(url=url, check_compatibility=False)
    await client.create_collection(
        name, vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE)
    )
    try:
        await client.upsert(
            name,
            points=[
                models.PointStruct(
                    id=index,
                    vector=[1.0, 0.0],
                    payload={"canonical_document_id": document, "corpus_tier": "gold"},
                )
                for index, document in enumerate(["bad-doc", "good-doc"], start=1)
            ],
            wait=True,
        )
        found = await client.query_points(
            name,
            query=[1.0, 0.0],
            query_filter=RetrievalFilters(corpus_tiers=["gold"]).to_qdrant(),
            limit=5,
        )
        assert [point.id for point in found.points] == [2]
    finally:
        await client.delete_collection(name)
        await client.close()


@pytest.mark.asyncio
async def test_an_unknown_exclusion_list_stops_the_boot(monkeypatch) -> None:
    async def broken():
        raise RuntimeError("database is down")

    monkeypatch.setattr(quarantine, "refresh", broken)
    with pytest.raises(RuntimeError):
        await quarantine.start()
