from __future__ import annotations

import pytest

from app.services.fast_research import FastLegalResearchService
from app.services.retrieval import RetrievalHit, RetrievalTimings


class FakeRetrieval:
    def __init__(self, hits: list[RetrievalHit]) -> None:
        self.hits = hits
        self.calls: list[dict] = []

    async def search_with_timings(self, query: str, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return self.hits, RetrievalTimings(
            embedding_ms=420.0,
            qdrant_ms=35.0,
            reranking_ms=0.0,
            total_ms=455.0,
            embedding_cache_hit=True,
        )


def hit(chunk_id: str, document_id: str, title: str, *, current: bool) -> RetrievalHit:
    return RetrievalHit(
        point_id=chunk_id,
        payload={
            "chunk_id": chunk_id,
            "canonical_document_id": document_id,
            "title": title,
            "source_type": "act",
            "act_name": title,
            "section": "154",
            "page_start": 4,
            "page_end": 5,
            "text": "The supplied Gold passage states when police must record information and the procedural requirement.",
            "is_current": current,
        },
        dense_score=0.8,
        sparse_score=4.0,
        fused_score=0.7,
        reranker_score=0.7,
    )


@pytest.mark.asyncio
async def test_fast_research_is_retrieval_only_and_exposes_currency_warning() -> None:
    retrieval = FakeRetrieval([
        hit("chunk-a", "doc-a", "Official Procedure Act", current=True),
        hit("chunk-b", "doc-b", "Official Amendment", current=False),
    ])
    service = FastLegalResearchService(retrieval)  # type: ignore[arg-type]

    result = await service.run(
        query="When must police record information?",
        role="citizen",
        case_id=None,
        history=[],
    )

    assert retrieval.calls[0]["candidate_limit"] == 8
    assert retrieval.calls[0]["result_limit"] == 8
    assert retrieval.calls[0]["rerank"] is False
    assert "does not synthesise a final legal opinion" in result["final_answer"]
    assert "Currency notice" in result["final_answer"]
    assert [item.chunk_id for item in result["citations"]] == ["chunk-a", "chunk-b"]
    assert result["agent_trace"][0].details["no_generative_claims"] is True
    assert result["timings"]["embedding_cache_hit"] is True
    assert result["timings"]["reranking_ms"] == 0


@pytest.mark.asyncio
async def test_fast_research_abstains_when_no_gold_evidence_is_found() -> None:
    result = await FastLegalResearchService(FakeRetrieval([])).run(  # type: ignore[arg-type]
        query="unsupported question", role="citizen", case_id=None, history=[]
    )

    assert result["citations"] == []
    assert result["confidence_score"] == 0
    assert result["evidence_strength"] == "insufficient"


@pytest.mark.asyncio
async def test_fast_research_rejects_missing_child_results_for_missing_pet_query() -> None:
    child_result = hit("child-a", "doc-child", "Procedure for missing children", current=True)
    child_result.payload["text"] = "Police shall register information and trace a missing child."
    result = await FastLegalResearchService(FakeRetrieval([child_result])).run(  # type: ignore[arg-type]
        query="How should I report a missing pet dog and request an FIR?",
        role="citizen",
        case_id=None,
        history=[],
    )

    assert result["citations"] == []
    assert result["confidence_score"] == 0
    assert result["evidence_strength"] == "insufficient"
    assert result["agent_trace"][0].details["result_count"] == 0


@pytest.mark.asyncio
async def test_fast_research_prefers_distinct_authorities_before_duplicate_passages() -> None:
    first = hit("doc-a-1", "doc-a", "Authority A", current=True)
    duplicate = hit("doc-a-2", "doc-a", "Authority A", current=True)
    second = hit("doc-b-1", "doc-b", "Authority B", current=True)
    third = hit("doc-c-1", "doc-c", "Authority C", current=True)
    fourth = hit("doc-d-1", "doc-d", "Authority D", current=True)
    result = await FastLegalResearchService(FakeRetrieval([first, duplicate, second, third, fourth])).run(  # type: ignore[arg-type]
        query="When must police record information?", role="citizen", case_id=None, history=[]
    )

    assert [item.chunk_id for item in result["citations"]] == ["doc-a-1", "doc-b-1", "doc-c-1", "doc-d-1"]
    assert result["agent_trace"][0].details["unique_document_count"] == 4


@pytest.mark.asyncio
async def test_fast_research_does_not_pad_with_duplicate_authorities() -> None:
    first = hit("doc-a-1", "", "Same authority", current=True)
    duplicate = hit("doc-a-2", "", "Same authority", current=True)
    result = await FastLegalResearchService(FakeRetrieval([first, duplicate])).run(  # type: ignore[arg-type]
        query="When must police record information?", role="citizen", case_id=None, history=[]
    )

    assert [item.chunk_id for item in result["citations"]] == ["doc-a-1"]
    assert result["agent_trace"][0].details["unique_document_count"] == 1
