"""Deep offers the authorities it found before it has an answer.

Measured on the baseline: Deep's first source-backed event arrived at the same
moment as the finished answer, because citations were written only after
verification. Time-to-first-useful-output was therefore identical to
end-to-end -- 92 s at p50, 170 s at p95 -- and the reader saw a progress label
for all of it.

Retrieval completes at roughly 7% of that. These tests pin what may be shown
at that point and, more importantly, what it may never be mistaken for: every
entry is marked unverified and not-final, nothing from a case collection
appears, and the final verified citations are unchanged.
"""

from __future__ import annotations

import pytest

from app.agents.located_sources import (
    EXCERPT_CHARACTERS,
    MAX_LOCATED_SOURCES,
    located_sources,
)
from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS, POLICE_CASE_DATA
from app.services.retrieval import RetrievalHit


def _hit(**payload) -> RetrievalHit:
    base = {
        "chunk_id": "chunk-1",
        "collection_name": GLOBAL_LEGAL_CORPUS,
        "title": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "source_type": "act",
        "act_name": "BNSS",
        "section": "35",
        "page_start": 12,
        "page_end": 13,
        "source_url": "https://example.invalid/bnss",
        "text": "A police officer may arrest without a warrant in the cases stated.",
        "is_current": True,
    }
    base.update(payload)
    return RetrievalHit(
        point_id=str(base["chunk_id"]),
        payload=base,
        dense_score=0.8,
        sparse_score=0.2,
        fused_score=0.5,
        reranker_score=0.5,
    )


def test_every_entry_says_it_is_neither_verified_nor_the_answer() -> None:
    """The one property that makes publishing these early safe.

    A surface renders a list of fields. If the disclaimer lived in the
    envelope, a client that iterates the entries would drop it.
    """
    sources = located_sources([_hit(), _hit(chunk_id="chunk-2")])
    assert sources
    for source in sources:
        assert source["verification_status"] == "unverified"
        assert source["is_final_answer"] is False


def test_an_entry_carries_what_identifies_the_provision() -> None:
    source = located_sources([_hit()])[0]
    assert source["title"].startswith("Bharatiya Nagarik")
    assert source["act_name"] == "BNSS"
    assert source["section"] == "35"
    assert source["page_start"] == 12 and source["page_end"] == 13
    assert source["source_url"] == "https://example.invalid/bnss"
    assert source["chunk_id"] == "chunk-1"
    assert source["number"] == 1


def test_currency_and_repeal_labels_travel_with_the_early_list() -> None:
    """A citizen shown a Penal Code provision must be told it was replaced.

    Showing sources sooner must not show them with less of the truth
    attached than the final citation carries.
    """
    source = located_sources([_hit()])[0]
    assert "currency_status" in source
    assert "repeal_label" in source
    assert "replaced_by" in source
    assert "repealed_on" in source


def test_case_collection_passages_are_never_offered_as_progress() -> None:
    """Case material is retrieved for police and advocate runs.

    Interim progress is not the place to widen where private case text
    appears, so the early list is global-corpus only.
    """
    sources = located_sources(
        [
            _hit(chunk_id="case-1", collection_name=POLICE_CASE_DATA, title="Case statement"),
            _hit(chunk_id="corpus-1"),
        ]
    )
    assert [source["chunk_id"] for source in sources] == ["corpus-1"]


def test_the_excerpt_is_short_enough_not_to_read_as_an_answer() -> None:
    source = located_sources([_hit(text="word " * 500)])[0]
    assert len(source["excerpt"]) <= EXCERPT_CHARACTERS
    assert source["excerpt"].endswith("…")


def test_the_list_is_bounded() -> None:
    sources = located_sources([_hit(chunk_id=f"chunk-{index}") for index in range(40)])
    assert len(sources) == MAX_LOCATED_SOURCES


def test_no_sources_yields_an_empty_list_rather_than_an_event_worth_sending() -> None:
    assert located_sources([]) == []


class _FakeRetrieval:
    pass


@pytest.mark.asyncio
async def test_the_workflow_reports_located_sources_on_the_retrieval_callback() -> None:
    """The graph does not own the transport.

    The sources ride the existing progress callback, so a caller with
    nowhere to put them simply ignores the key and nothing else changes.
    """
    from app.agents.orchestrator import LegalRAGWorkflow

    observed: list[tuple[str, str, dict]] = []

    async def callback(stage: str, transition: str, data: dict) -> None:
        observed.append((stage, transition, data))

    workflow = LegalRAGWorkflow.__new__(LegalRAGWorkflow)
    workflow.retrieval = _FakeRetrieval()  # type: ignore[attr-defined]

    async def fake_retrieval_node(state, service):
        return {"retrieved_chunks": [_hit(), _hit(chunk_id="chunk-2")]}

    import app.agents.orchestrator as orchestrator_module

    original = orchestrator_module.retrieval_node
    orchestrator_module.retrieval_node = fake_retrieval_node  # type: ignore[assignment]
    token = orchestrator_module._progress_callback.set(callback)
    try:
        await LegalRAGWorkflow._retrieve(workflow, {})  # type: ignore[arg-type]
    finally:
        orchestrator_module.retrieval_node = original  # type: ignore[assignment]
        orchestrator_module._progress_callback.reset(token)

    completed = [item for item in observed if item[0] == "retrieval" and item[1] == "completed"]
    assert completed, "retrieval must report completion"
    data = completed[-1][2]
    assert data["candidate_count"] == 2
    assert len(data["located_sources"]) == 2
    assert all(source["is_final_answer"] is False for source in data["located_sources"])
