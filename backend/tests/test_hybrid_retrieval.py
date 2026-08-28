from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from qdrant_client import models

from app.core.config import settings
from app.ingestion.embedder import EmbeddedText
from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS, POLICE_CASE_DATA
from app.services.retrieval import (
    HybridRetrievalService,
    RetrievalFilters,
    RetrievalTarget,
)


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], int]] = []

    def embed_texts(
        self,
        texts: list[str],
        *,
        batch_size: int,
    ) -> list[EmbeddedText]:
        self.calls.append((texts, batch_size))
        return [EmbeddedText(dense=[0.1, 0.2, 0.3], sparse={11: 0.8, 29: 0.4})]


class FakeReranker:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.calls: list[tuple[str, list[str]]] = []

    def score(self, query: str, documents: list[str]) -> list[float]:
        self.calls.append((query, documents))
        return self.scores


class FakeQdrantClient:
    def __init__(
        self,
        *,
        dense_points: list[Any],
        sparse_points: list[Any],
        fused_points: list[Any],
    ) -> None:
        self.dense_points = dense_points
        self.sparse_points = sparse_points
        self.fused_points = fused_points
        self.calls: list[dict[str, Any]] = []

    async def query_points(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if "prefetch" in kwargs:
            return SimpleNamespace(points=self.fused_points)
        if kwargs["using"] == settings.qdrant_dense_vector_name:
            return SimpleNamespace(points=self.dense_points)
        if kwargs["using"] == settings.qdrant_sparse_vector_name:
            return SimpleNamespace(points=self.sparse_points)
        raise AssertionError(f"Unexpected vector name: {kwargs['using']}")


def point(point_id: str, score: float, payload: dict[str, Any] | None = None) -> Any:
    return SimpleNamespace(id=point_id, score=score, payload=payload)


def conditions_by_key(query_filter: models.Filter) -> dict[str, models.FieldCondition]:
    return {
        condition.key: condition
        for condition in query_filter.must or []
        if isinstance(condition, models.FieldCondition)
    }


def test_retrieval_filters_convert_all_supported_fields() -> None:
    query_filter = RetrievalFilters(
        source_types=["judgment", "act"],
        courts=["Supreme Court of India"],
        jurisdictions=["India"],
        acts=["Bharatiya Nyaya Sanhita, 2023"],
        sections=["103"],
        year_from=2023,
        year_to=2026,
        date_from="2025-01-02",
        date_to="2025-12-30",
        current_only=True,
        corpus_tiers=["gold", "extended"],
    ).to_qdrant()

    assert query_filter is not None
    conditions = conditions_by_key(query_filter)
    assert conditions["source_type"].match.any == ["judgment", "act"]
    assert conditions["court"].match.any == ["Supreme Court of India"]
    assert conditions["jurisdiction"].match.any == ["India"]
    assert conditions["act_name"].match.any == ["Bharatiya Nyaya Sanhita, 2023"]
    assert conditions["section"].match.any == ["103"]
    assert conditions["corpus_tier"].match.any == ["gold", "extended"]
    assert conditions["decision_year"].range.gte == 2023
    assert conditions["decision_year"].range.lte == 2026
    assert conditions["decision_date"].range.gte.isoformat() == "2025-01-02T00:00:00+00:00"
    assert conditions["decision_date"].range.lte.isoformat() == "2025-12-30T23:59:59+00:00"
    assert conditions["is_current"].match.value is True


def test_retrieval_filters_default_to_verified_global_tiers_and_can_be_disabled() -> None:
    default_filter = RetrievalFilters().to_qdrant()
    assert default_filter is not None
    default_conditions = conditions_by_key(default_filter)
    assert default_conditions["corpus_tier"].match.any == ["gold", "extended"]

    assert RetrievalFilters(corpus_tiers=[]).to_qdrant() is None


@pytest.mark.asyncio
async def test_hybrid_search_preserves_channel_scores_and_uses_reranker_order() -> None:
    client = FakeQdrantClient(
        dense_points=[point("a", 0.91), point("b", 0.72)],
        sparse_points=[point("b", 8.4), point("c", 6.3)],
        fused_points=[
            point("a", 0.75, {"text": "first passage", "title": "A"}),
            point("b", 0.95, {"text": "second passage", "title": "B"}),
            point("c", 0.60, {"text": "third passage", "title": "C"}),
        ],
    )
    embedder = FakeEmbedder()
    reranker = FakeReranker([0.25, 0.99, 0.50])
    filters = RetrievalFilters(courts=["Supreme Court of India"])
    service = HybridRetrievalService(
        client=client,
        embedder=embedder,
        reranker=reranker,
    )

    hits = await service.search(
        "criminal intent",
        filters=filters,
        candidate_limit=7,
        result_limit=2,
    )

    assert embedder.calls == [(["criminal intent"], 1)]
    assert reranker.calls == [
        ("criminal intent", ["first passage", "second passage", "third passage"])
    ]
    assert [hit.point_id for hit in hits] == ["b", "c"]
    assert hits[0].dense_score == pytest.approx(0.72)
    assert hits[0].sparse_score == pytest.approx(8.4)
    assert hits[0].fused_score == pytest.approx(0.95)
    assert hits[0].reranker_score == pytest.approx(0.99)
    assert hits[1].dense_score is None
    assert hits[1].sparse_score == pytest.approx(6.3)
    assert hits[1].fused_score == pytest.approx(0.60)
    assert hits[1].reranker_score == pytest.approx(0.50)

    assert len(client.calls) == 3
    assert all(call["collection_name"] == GLOBAL_LEGAL_CORPUS for call in client.calls)
    dense_call = next(
        call for call in client.calls if call.get("using") == settings.qdrant_dense_vector_name
    )
    sparse_call = next(
        call for call in client.calls if call.get("using") == settings.qdrant_sparse_vector_name
    )
    fused_call = next(call for call in client.calls if "prefetch" in call)
    assert dense_call["with_payload"] is False
    assert sparse_call["with_payload"] is False
    assert fused_call["with_payload"] is True
    assert fused_call["query"].fusion == models.Fusion.RRF
    assert len(fused_call["prefetch"]) == 2
    assert all(call["limit"] == 7 for call in client.calls)
    assert all(call.get("query_filter") is not None for call in (dense_call, sparse_call))
    assert all(prefetch.filter is not None for prefetch in fused_call["prefetch"])


@pytest.mark.asyncio
async def test_hybrid_search_returns_empty_results_without_loading_reranker() -> None:
    client = FakeQdrantClient(dense_points=[], sparse_points=[], fused_points=[])
    embedder = FakeEmbedder()
    reranker = FakeReranker([])
    service = HybridRetrievalService(
        client=client,
        embedder=embedder,
        reranker=reranker,
    )

    hits = await service.search("no matching authority")

    assert hits == []
    assert reranker.calls == [("no matching authority", [])]
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_fast_search_skips_reranker_and_reuses_hashed_embedding_cache() -> None:
    client = FakeQdrantClient(
        dense_points=[point("a", 0.8)],
        sparse_points=[point("a", 4.2)],
        fused_points=[point("a", 0.72, {"text": "gold authority", "title": "A"})],
    )
    embedder = FakeEmbedder()
    reranker = FakeReranker([0.99])
    service = HybridRetrievalService(client=client, embedder=embedder, reranker=reranker)

    first, first_timings = await service.search_with_timings(
        "  Article 14   equality ", candidate_limit=8, result_limit=1, rerank=False
    )
    second, second_timings = await service.search_with_timings(
        "article 14 equality", candidate_limit=8, result_limit=1, rerank=False
    )

    assert len(embedder.calls) == 1
    assert reranker.calls == []
    assert first[0].reranker_score == pytest.approx(first[0].fused_score)
    assert second[0].point_id == "a"
    assert first_timings.embedding_cache_hit is False
    assert second_timings.embedding_cache_hit is True
    assert first_timings.reranking_ms == 0
    assert second_timings.reranking_ms == 0


@pytest.mark.asyncio
async def test_scoped_search_embeds_once_and_reranks_global_and_private_together() -> None:
    class ScopedClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def query_points(self, **kwargs: Any) -> Any:
            self.calls.append(kwargs)
            collection = kwargs["collection_name"]
            if "prefetch" not in kwargs:
                score = 0.8 if collection == GLOBAL_LEGAL_CORPUS else 0.7
                return SimpleNamespace(points=[point(f"{collection}-id", score)])
            payload = {
                "text": "public authority" if collection == GLOBAL_LEGAL_CORPUS else "private fact",
                "case_id": None if collection == GLOBAL_LEGAL_CORPUS else "case-a",
            }
            return SimpleNamespace(points=[point(f"{collection}-id", 0.5, payload)])

    client = ScopedClient()
    embedder = FakeEmbedder()
    reranker = FakeReranker([0.4, 0.95])
    service = HybridRetrievalService(client=client, embedder=embedder, reranker=reranker)

    hits, _ = await service.search_across_collections_with_timings(
        "missing dog complaint",
        targets=[
            RetrievalTarget(GLOBAL_LEGAL_CORPUS, RetrievalFilters()),
            RetrievalTarget(
                POLICE_CASE_DATA,
                RetrievalFilters(corpus_tiers=[], case_ids=["case-a"]),
            ),
        ],
        candidate_limit=5,
        result_limit=2,
    )

    assert embedder.calls == [(["missing dog complaint"], 1)]
    assert len(client.calls) == 6
    assert [hit.payload["collection_name"] for hit in hits] == [
        POLICE_CASE_DATA,
        GLOBAL_LEGAL_CORPUS,
    ]
    private_calls = [
        call for call in client.calls if call["collection_name"] == POLICE_CASE_DATA
    ]
    private_filter = private_calls[0]["query_filter"]
    assert conditions_by_key(private_filter)["case_id"].match.any == ["case-a"]
