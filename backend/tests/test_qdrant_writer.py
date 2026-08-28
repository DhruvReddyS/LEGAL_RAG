from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from qdrant_client import models

from app.ingestion.chunker import LegalChunk
from app.ingestion.embedder import EmbeddedText
from app.ingestion.qdrant_writer import _point_id, replace_document_chunks


def _chunk(chunk_id: str) -> LegalChunk:
    return LegalChunk(
        chunk_id=chunk_id,
        document_id="gold-doc-test",
        canonical_document_id="gold-canonical-test",
        source_id="url:test",
        title="Test Act",
        source_type="ACT",
        jurisdiction="India",
        page_start=1,
        page_end=1,
        current_status="current",
        verified_official=True,
        quality_status="verified",
        text=f"Provision for {chunk_id}",
    )


def _embedding(seed: int) -> EmbeddedText:
    return EmbeddedText(dense=[float(seed)], sparse={seed: 1.0})


class FakeQdrant:
    def __init__(self, scroll_pages: list[tuple[list[Any], Any]]) -> None:
        self.scroll_pages = iter(scroll_pages)
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def upsert(self, **kwargs: Any) -> None:
        self.events.append(("upsert", kwargs))

    async def scroll(self, **kwargs: Any) -> tuple[list[Any], Any]:
        self.events.append(("scroll", kwargs))
        return next(self.scroll_pages)

    async def delete(self, **kwargs: Any) -> None:
        self.events.append(("delete", kwargs))


@pytest.mark.asyncio
async def test_replacement_upserts_every_batch_before_deleting_only_stale_points() -> None:
    chunks = [_chunk("chunk-a"), _chunk("chunk-b"), _chunk("chunk-c")]
    current_ids = [_point_id(chunk.chunk_id) for chunk in chunks]
    stale_ids = ["3f22d608-68de-4bb1-8ed1-f69b5ecf6280", "9a5eb310-106e-4ea7-b249-f555fc18a783"]
    client = FakeQdrant(
        [
            ([SimpleNamespace(id=current_ids[0]), SimpleNamespace(id=stale_ids[0])], "next"),
            ([SimpleNamespace(id=current_ids[2]), SimpleNamespace(id=stale_ids[1])], None),
        ]
    )

    count = await replace_document_chunks(
        client,  # type: ignore[arg-type]
        chunks,
        [_embedding(1), _embedding(2), _embedding(3)],
        batch_size=2,
    )

    assert count == 3
    assert [name for name, _ in client.events] == [
        "upsert",
        "upsert",
        "scroll",
        "scroll",
        "delete",
    ]
    assert [len(event[1]["points"]) for event in client.events[:2]] == [2, 1]
    assert client.events[3][1]["offset"] == "next"
    selector = client.events[-1][1]["points_selector"]
    assert isinstance(selector, models.PointIdsList)
    assert set(selector.points) == set(stale_ids)


@pytest.mark.asyncio
async def test_failed_upsert_never_starts_stale_cleanup() -> None:
    class FailingQdrant(FakeQdrant):
        async def upsert(self, **kwargs: Any) -> None:
            self.events.append(("upsert", kwargs))
            if len(self.events) == 2:
                raise RuntimeError("simulated durable-write failure")

    client = FailingQdrant([])
    chunks = [_chunk("chunk-a"), _chunk("chunk-b")]

    with pytest.raises(RuntimeError, match="durable-write failure"):
        await replace_document_chunks(
            client,  # type: ignore[arg-type]
            chunks,
            [_embedding(1), _embedding(2)],
            batch_size=1,
        )

    assert [name for name, _ in client.events] == ["upsert", "upsert"]

