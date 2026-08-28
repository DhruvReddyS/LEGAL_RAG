from __future__ import annotations

import uuid

from qdrant_client import AsyncQdrantClient, models

from app.core.config import settings
from app.ingestion.chunker import LegalChunk
from app.ingestion.embedder import EmbeddedText
from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS
from app.ingestion.sparse import to_sparse_vector


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def _payload(chunk: LegalChunk) -> dict[str, object]:
    payload: dict[str, object] = {
        "chunk_id": chunk.chunk_id,
        "text": chunk.text,
        "source_type": chunk.source_type,
        "title": chunk.title,
        "act_name": chunk.act_name or "",
        "section": chunk.section or "",
        "subsection": chunk.subsection or "",
        "jurisdiction": chunk.jurisdiction or "",
        "court": chunk.court or "",
        "decision_year": chunk.decision_year or 0,
        "is_current": chunk.is_current,
        "source_id": chunk.source_id,
        "document_id": chunk.document_id,
        "canonical_document_id": chunk.canonical_document_id,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "heading_path": chunk.heading_path,
        "verified_official": chunk.verified_official,
        "quality_status": chunk.quality_status,
        "corpus_tier": "gold",
    }
    if chunk.decision_date:
        payload["decision_date"] = f"{chunk.decision_date}T00:00:00Z"
    return payload


async def replace_document_chunks(
    client: AsyncQdrantClient,
    chunks: list[LegalChunk],
    embeddings: list[EmbeddedText],
    *,
    batch_size: int = 64,
) -> int:
    if not chunks:
        return 0
    if len(chunks) != len(embeddings):
        raise ValueError("Chunk and embedding counts differ")
    canonical_document_id = chunks[0].canonical_document_id
    points = [
        models.PointStruct(
            id=_point_id(chunk.chunk_id),
            vector={
                settings.qdrant_dense_vector_name: embedding.dense,
                settings.qdrant_sparse_vector_name: to_sparse_vector(embedding.sparse),
            },
            payload=_payload(chunk),
        )
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]
    for offset in range(0, len(points), batch_size):
        await client.upsert(
            collection_name=GLOBAL_LEGAL_CORPUS,
            points=points[offset : offset + batch_size],
            wait=True,
        )
    # Upsert the complete replacement first. Only after every batch is durable
    # do we remove point IDs that belonged to an older chunking version.
    current_point_ids = {str(point.id) for point in points}
    document_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="canonical_document_id",
                match=models.MatchValue(value=canonical_document_id),
            )
        ]
    )
    stale_point_ids: list[str] = []
    scroll_offset: models.ExtendedPointId | None = None
    while True:
        existing, scroll_offset = await client.scroll(
            collection_name=GLOBAL_LEGAL_CORPUS,
            scroll_filter=document_filter,
            limit=256,
            offset=scroll_offset,
            with_payload=False,
            with_vectors=False,
        )
        stale_point_ids.extend(
            str(point.id) for point in existing if str(point.id) not in current_point_ids
        )
        if scroll_offset is None:
            break
    if stale_point_ids:
        await client.delete(
            collection_name=GLOBAL_LEGAL_CORPUS,
            points_selector=models.PointIdsList(points=stale_point_ids),
            wait=True,
        )
    return len(points)
