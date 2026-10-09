"""The serving path made three Qdrant queries per target to answer one question.

`_query_target` issued a dense-only query, a sparse-only query and a fused
query. The fused query carries its own dense and sparse prefetch, so it needs
neither of the other two to produce its results. They existed solely to report
what each lane thought of a candidate, and `dense_score` and `sparse_score` are
read by exactly two places: the `/retrieval` diagnostic endpoints and
`retrieval_smoke`. Nothing in ranking, fusion, reranking, the relevance gates,
verification or citation construction reads them.

They run concurrently, so the wall-clock cost is small -- Fast measured 24 ms
at p50 for its whole Qdrant stage. The work is still real and it is per
request: Deep with a case-scoped target issued six queries where two answer
the question. That is the number that matters when more than one person asks
at once, which is this deployment's actual constraint, with one Ollama slot
and a 24 GB host.

These tests use a fake client and reach no Qdrant, no embedder and no model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS
from app.services.retrieval import (
    HybridRetrievalService,
    RetrievalFilters,
    RetrievalTarget,
)


@dataclass
class _Point:
    id: str
    score: float
    payload: dict[str, Any] | None = None


class _Response:
    def __init__(self, points):
        self.points = points


class _CountingClient:
    """Records every query_points call and what it was asked for."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def query_points(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("prefetch") is not None:
            return _Response([_Point("p1", 0.5, {"chunk_id": "c1", "text": "A provision."})])
        return _Response([_Point("p1", 0.9)])

    @property
    def fused_calls(self) -> list[dict[str, Any]]:
        return [call for call in self.calls if call.get("prefetch") is not None]

    @property
    def lane_calls(self) -> list[dict[str, Any]]:
        return [call for call in self.calls if call.get("prefetch") is None]


@pytest.fixture
def service() -> HybridRetrievalService:
    instance = HybridRetrievalService.__new__(HybridRetrievalService)
    instance.client = _CountingClient()  # type: ignore[assignment]
    return instance


async def _query(service, *, with_lane_scores):
    return await service._query_target(
        target=RetrievalTarget(GLOBAL_LEGAL_CORPUS, RetrievalFilters()),
        dense_query=[0.1] * 4,
        sparse_query={"indices": [1], "values": [1.0]},
        candidate_limit=10,
        with_lane_scores=with_lane_scores,
    )


@pytest.mark.asyncio
async def test_the_serving_path_makes_one_query_per_target(service) -> None:
    """One, not three. This is the whole change."""
    await _query(service, with_lane_scores=False)
    assert len(service.client.calls) == 1
    assert len(service.client.fused_calls) == 1
    assert service.client.lane_calls == []


@pytest.mark.asyncio
async def test_the_diagnostic_path_still_makes_all_three(service) -> None:
    """The capability is moved, not removed."""
    await _query(service, with_lane_scores=True)
    assert len(service.client.calls) == 3
    assert len(service.client.fused_calls) == 1
    assert len(service.client.lane_calls) == 2


@pytest.mark.asyncio
async def test_the_candidates_are_identical_either_way(service) -> None:
    """The fused query is untouched, so ranking cannot move.

    This is the property that makes the change safe: results come from the
    fused query alone, before and after.
    """
    points_without, _, _ = await _query(service, with_lane_scores=False)
    service.client = _CountingClient()  # type: ignore[assignment]
    points_with, _, _ = await _query(service, with_lane_scores=True)
    assert [point.id for point in points_without] == [point.id for point in points_with]
    assert [point.score for point in points_without] == [point.score for point in points_with]


@pytest.mark.asyncio
async def test_lane_scores_are_absent_rather_than_wrong_on_the_serving_path(service) -> None:
    """Absent is an existing state, not a new one.

    `RetrievalHit.dense_score` and `.sparse_score` are already `float | None`,
    and a candidate that one lane did not return has always had None there.
    """
    _, dense, sparse = await _query(service, with_lane_scores=False)
    assert dense == {}
    assert sparse == {}

    service.client = _CountingClient()  # type: ignore[assignment]
    _, dense, sparse = await _query(service, with_lane_scores=True)
    assert dense == {"p1": pytest.approx(0.9)}
    assert sparse == {"p1": pytest.approx(0.9)}


@pytest.mark.asyncio
async def test_the_fused_query_still_asks_for_payloads_and_the_lanes_never_did(service) -> None:
    """The lane queries fetched no payload, which is why they were cheap.

    Worth pinning: if they ever started fetching payloads, removing them
    would be a much larger saving and keeping them a much larger cost.
    """
    await _query(service, with_lane_scores=True)
    assert service.client.fused_calls[0]["with_payload"] is True
    assert all(call["with_payload"] is False for call in service.client.lane_calls)


def test_the_serving_lanes_do_not_ask_for_lane_scores() -> None:
    """Fast, Deep and the advocate flow must leave the default alone.

    The flag defaults to off, so this reads the call sites: a lane that
    started passing `with_lane_scores=True` would silently restore three
    queries per target.
    """
    import inspect

    from app.agents import defence_strategy_agent, retrieval_agent
    from app.services import fast_research

    for module in (fast_research, retrieval_agent, defence_strategy_agent):
        source = inspect.getsource(module)
        assert "with_lane_scores" not in source, (
            f"{module.__name__} asks for lane scores; nothing in the serving "
            "path reads dense_score or sparse_score"
        )


def test_the_two_readers_of_lane_scores_do_ask_for_them() -> None:
    """And the diagnostic surfaces must keep asking, or they report blanks."""
    import inspect

    from app.ingestion import retrieval_smoke
    from app.routers import retrieval as retrieval_router

    for module in (retrieval_router, retrieval_smoke):
        source = inspect.getsource(module)
        assert "with_lane_scores=True" in source, (
            f"{module.__name__} reports per-lane scores but no longer asks for them"
        )
