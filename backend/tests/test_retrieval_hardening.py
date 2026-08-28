from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

import main as main_module
from app.ingestion.embedder import EmbeddedText
from app.schemas.retrieval import RetrievalFilterRequest, RetrievalRequest
from app.services.retrieval import BGEReranker, HybridRetrievalService


@pytest.mark.parametrize("query", ["", " ", "\t\n"])
def test_retrieval_request_rejects_blank_queries(query: str) -> None:
    with pytest.raises(ValidationError, match="query must not be blank"):
        RetrievalRequest(query=query)


def test_retrieval_request_strips_query_and_accepts_exact_iso_dates() -> None:
    request = RetrievalRequest(
        query="  section 103 punishment  ",
        filters={"date_from": "2024-01-01", "date_to": "2024-12-31"},
    )

    assert request.query == "section 103 punishment"
    assert request.filters.date_from.isoformat() == "2024-01-01"
    assert request.filters.date_to.isoformat() == "2024-12-31"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"date_from": "01-01-2024"}, "date_from"),
        (
            {"date_from": "2025-01-01", "date_to": "2024-01-01"},
            "date_from must be less than or equal to date_to",
        ),
        (
            {"year_from": 2025, "year_to": 2024},
            "year_from must be less than or equal to year_to",
        ),
    ],
)
def test_retrieval_filters_reject_invalid_dates_and_ranges(
    payload: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        RetrievalFilterRequest(**payload)


def test_retrieval_request_rejects_result_limit_above_candidate_limit() -> None:
    with pytest.raises(
        ValidationError,
        match="result_limit must be less than or equal to candidate_limit",
    ):
        RetrievalRequest(query="bail", candidate_limit=5, result_limit=6)


def test_reranker_uses_full_supported_context_with_bounded_batch() -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.options: dict[str, Any] = {}

        def compute_score(self, pairs: list[list[str]], **options: Any) -> list[float]:
            self.options = options
            return [0.75] * len(pairs)

    model = FakeModel()
    reranker = BGEReranker()
    reranker._model = model

    assert reranker.score("query", ["word " * 700]) == [0.75]
    assert model.options["max_length"] == 8192
    assert model.options["batch_size"] == 2


class BlockingEmbedder:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    def embed_texts(self, texts: list[str], *, batch_size: int) -> list[EmbeddedText]:
        import time

        self.active += 1
        self.max_active = max(self.max_active, self.active)
        time.sleep(0.03)
        self.active -= 1
        return [EmbeddedText(dense=[0.1], sparse={1: 0.2})]


class EmptyClient:
    async def query_points(self, **kwargs: Any) -> Any:
        return SimpleNamespace(points=[])


class EmptyReranker:
    def score(self, query: str, documents: list[str]) -> list[float]:
        return []


@pytest.mark.asyncio
async def test_inference_concurrency_is_bounded_across_searches() -> None:
    embedder = BlockingEmbedder()
    service = HybridRetrievalService(
        client=EmptyClient(),
        embedder=embedder,
        reranker=EmptyReranker(),
        inference_concurrency=1,
    )

    await asyncio.gather(service.search("first"), service.search("second"))

    assert embedder.max_active == 1


@pytest.mark.asyncio
async def test_embedding_lane_is_not_blocked_by_reranking_lane() -> None:
    service = HybridRetrievalService(
        client=EmptyClient(),
        embedder=BlockingEmbedder(),
        reranker=EmptyReranker(),
        inference_concurrency=1,
    )

    async with service._reranking_slots:
        result = await asyncio.wait_for(service.embed_documents(["fast query"]), timeout=0.2)

    assert len(result) == 1


@pytest.mark.asyncio
async def test_application_lifespan_owns_one_service_and_closes_it(monkeypatch) -> None:
    instances: list[Any] = []

    class FakeService:
        def __init__(self) -> None:
            self.closed = False
            self.warmed = False
            instances.append(self)

        async def warmup(self) -> None:
            self.warmed = True

        async def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(main_module, "HybridRetrievalService", FakeService)

    async with main_module.lifespan(main_module.app):
        assert len(instances) == 1
        assert main_module.app.state.retrieval_service is instances[0]
        assert instances[0].closed is False
        assert instances[0].warmed is True

    assert instances[0].closed is True
