from __future__ import annotations

import asyncio
import gc
import hashlib
from collections import OrderedDict
from time import perf_counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.core.config import settings
from app.core.qdrant import create_qdrant_client
from app.ingestion.embedder import BGEM3Embedder, resolve_embedding_device
from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS
from app.ingestion.sparse import to_sparse_vector


@dataclass
class RetrievalFilters:
    source_types: list[str] = field(default_factory=list)
    courts: list[str] = field(default_factory=list)
    jurisdictions: list[str] = field(default_factory=list)
    acts: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    year_from: int | None = None
    year_to: int | None = None
    date_from: date | str | None = None
    date_to: date | str | None = None
    current_only: bool = False
    corpus_tiers: list[str] = field(default_factory=lambda: ["gold", "extended"])
    case_ids: list[str] = field(default_factory=list)

    def to_qdrant(self) -> models.Filter | None:
        conditions: list[models.Condition] = []
        keyword_filters = {
            "source_type": self.source_types,
            "court": self.courts,
            "jurisdiction": self.jurisdictions,
            "act_name": self.acts,
            "section": self.sections,
            "corpus_tier": self.corpus_tiers,
            "case_id": self.case_ids,
        }
        for field_name, values in keyword_filters.items():
            if values:
                conditions.append(
                    models.FieldCondition(
                        key=field_name,
                        match=models.MatchAny(any=values),
                    )
                )
        if self.year_from is not None or self.year_to is not None:
            conditions.append(
                models.FieldCondition(
                    key="decision_year",
                    range=models.Range(gte=self.year_from, lte=self.year_to),
                )
            )
        if self.date_from is not None or self.date_to is not None:
            date_from = self._as_boundary(self.date_from, end_of_day=False)
            date_to = self._as_boundary(self.date_to, end_of_day=True)
            conditions.append(
                models.FieldCondition(
                    key="decision_date",
                    range=models.DatetimeRange(gte=date_from, lte=date_to),
                )
            )
        if self.current_only:
            conditions.append(
                models.FieldCondition(key="is_current", match=models.MatchValue(value=True))
            )
        return models.Filter(must=conditions) if conditions else None

    @staticmethod
    def _as_boundary(value: date | str | None, *, end_of_day: bool) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            value = date.fromisoformat(value)
        boundary = time(23, 59, 59) if end_of_day else time.min
        return datetime.combine(value, boundary, tzinfo=timezone.utc)


@dataclass
class RetrievalHit:
    point_id: str
    payload: dict[str, Any]
    dense_score: float | None
    sparse_score: float | None
    fused_score: float
    reranker_score: float


@dataclass
class RetrievalTimings:
    embedding_ms: float
    qdrant_ms: float
    reranking_ms: float
    total_ms: float
    embedding_cache_hit: bool = False


@dataclass(frozen=True)
class RetrievalTarget:
    collection_name: str
    filters: RetrievalFilters


class BGEReranker:
    # bge-reranker-v2-m3 supports an 8192-token context. Using that full context
    # prevents the current 700-word legal chunks from being silently cut down to
    # FlagEmbedding's much smaller default. A batch of two bounds peak memory.
    MAX_LENGTH = 8192
    BATCH_SIZE = 2

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        self.model_name = model_name
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            from FlagEmbedding import FlagReranker

            device = resolve_embedding_device()
            self._model = FlagReranker(
                self.model_name,
                use_fp16=device in {"cuda", "mps"},
                devices=device,
            )
        return self._model

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        scores = self._load().compute_score(
            [[query, document] for document in documents],
            batch_size=self.BATCH_SIZE,
            max_length=self.MAX_LENGTH,
            normalize=True,
        )
        if isinstance(scores, float):
            return [scores]
        return [float(score) for score in scores]

    def close(self) -> None:
        self._model = None


class HybridRetrievalService:
    def __init__(
        self,
        *,
        client: AsyncQdrantClient | None = None,
        embedder: BGEM3Embedder | None = None,
        reranker: BGEReranker | None = None,
        inference_concurrency: int = 1,
    ) -> None:
        if inference_concurrency < 1:
            raise ValueError("inference_concurrency must be at least 1")
        self.client = client or create_qdrant_client()
        self._owns_client = client is None
        self.embedder = embedder or BGEM3Embedder()
        self.reranker = reranker or BGEReranker()
        # Query embeddings and cross-encoder reranking use different models.
        # Separate queues prevent a long Deep rerank from head-of-line blocking
        # the latency-sensitive Fast embedding path.
        self._embedding_slots = asyncio.Semaphore(inference_concurrency)
        self._reranking_slots = asyncio.Semaphore(inference_concurrency)
        self._query_embedding_cache: OrderedDict[str, Any] = OrderedDict()
        self._query_embedding_cache_limit = settings.query_embedding_cache_size
        self._closed = False

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            await self.client.close()
        close_reranker = getattr(self.reranker, "close", None)
        if callable(close_reranker):
            close_reranker()
        self._query_embedding_cache.clear()
        # BGEM3Embedder has no public lifecycle API. It is application-owned here,
        # so releasing its lazy model on shutdown is safe and avoids retaining
        # accelerator memory during graceful worker replacement.
        if isinstance(self.embedder, BGEM3Embedder):
            self.embedder._model = None
        gc.collect()

    async def embed_documents(
        self, texts: list[str], *, batch_size: int = 8
    ) -> list[Any]:
        """Reuse the application-owned embedder without concurrent model access."""
        if self._closed:
            raise RuntimeError("retrieval service is closed")
        async with self._embedding_slots:
            return await asyncio.to_thread(
                self.embedder.embed_texts, texts, batch_size=batch_size
            )

    async def warmup(self) -> None:
        """Load the query embedder before readiness so the first user avoids cold-start latency."""
        await self.embed_documents(["legal corpus retrieval readiness"], batch_size=1)

    async def search(
        self,
        query: str,
        *,
        filters: RetrievalFilters | None = None,
        candidate_limit: int = 20,
        result_limit: int = 5,
        rerank: bool = True,
    ) -> list[RetrievalHit]:
        hits, _ = await self.search_with_timings(
            query,
            filters=filters,
            candidate_limit=candidate_limit,
            result_limit=result_limit,
            rerank=rerank,
        )
        return hits

    async def search_with_timings(
        self,
        query: str,
        *,
        filters: RetrievalFilters | None = None,
        candidate_limit: int = 20,
        result_limit: int = 5,
        rerank: bool = True,
    ) -> tuple[list[RetrievalHit], RetrievalTimings]:
        if self._closed:
            raise RuntimeError("retrieval service is closed")
        if not query.strip():
            raise ValueError("query must not be blank")
        if candidate_limit < 1:
            raise ValueError("candidate_limit must be at least 1")
        if result_limit < 1 or result_limit > candidate_limit:
            raise ValueError("result_limit must be between 1 and candidate_limit")

        return await self.search_across_collections_with_timings(
            query,
            targets=[
                RetrievalTarget(
                    collection_name=GLOBAL_LEGAL_CORPUS,
                    filters=filters or RetrievalFilters(),
                )
            ],
            candidate_limit=candidate_limit,
            result_limit=result_limit,
            rerank=rerank,
        )

    async def _query_target(
        self,
        *,
        target: RetrievalTarget,
        dense_query: list[float],
        sparse_query: models.SparseVector,
        candidate_limit: int,
    ) -> tuple[list[Any], dict[str, float], dict[str, float]]:
        query_filter = target.filters.to_qdrant()
        prefetch = [
            models.Prefetch(
                query=dense_query,
                using=settings.qdrant_dense_vector_name,
                filter=query_filter,
                limit=candidate_limit,
            ),
            models.Prefetch(
                query=sparse_query,
                using=settings.qdrant_sparse_vector_name,
                filter=query_filter,
                limit=candidate_limit,
            ),
        ]
        dense_response, sparse_response, fused_response = await asyncio.gather(
            self.client.query_points(
                collection_name=target.collection_name,
                query=dense_query,
                using=settings.qdrant_dense_vector_name,
                query_filter=query_filter,
                limit=candidate_limit,
                with_payload=False,
            ),
            self.client.query_points(
                collection_name=target.collection_name,
                query=sparse_query,
                using=settings.qdrant_sparse_vector_name,
                query_filter=query_filter,
                limit=candidate_limit,
                with_payload=False,
            ),
            self.client.query_points(
                collection_name=target.collection_name,
                prefetch=prefetch,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=candidate_limit,
                with_payload=True,
            ),
        )
        dense_scores = {str(point.id): float(point.score) for point in dense_response.points}
        sparse_scores = {str(point.id): float(point.score) for point in sparse_response.points}
        for point in fused_response.points:
            point.payload = dict(point.payload or {})
            point.payload["collection_name"] = target.collection_name
        return fused_response.points, dense_scores, sparse_scores

    async def search_across_collections_with_timings(
        self,
        query: str,
        *,
        targets: list[RetrievalTarget],
        candidate_limit: int = 20,
        result_limit: int = 5,
        rerank: bool = True,
    ) -> tuple[list[RetrievalHit], RetrievalTimings]:
        if self._closed:
            raise RuntimeError("retrieval service is closed")
        if not query.strip():
            raise ValueError("query must not be blank")
        if not targets:
            raise ValueError("at least one retrieval target is required")
        if candidate_limit < 1:
            raise ValueError("candidate_limit must be at least 1")
        if result_limit < 1 or result_limit > candidate_limit:
            raise ValueError("result_limit must be between 1 and candidate_limit")
        if len({target.collection_name for target in targets}) != len(targets):
            raise ValueError("retrieval target collections must be unique")

        started = perf_counter()
        embedding_started = perf_counter()
        cache_key = hashlib.sha256(" ".join(query.casefold().split()).encode("utf-8")).hexdigest()
        query_embedding = self._query_embedding_cache.get(cache_key)
        embedding_cache_hit = query_embedding is not None
        if query_embedding is None:
            async with self._embedding_slots:
                query_embedding = (
                    await asyncio.to_thread(self.embedder.embed_texts, [query], batch_size=1)
                )[0]
            if self._query_embedding_cache_limit:
                self._query_embedding_cache[cache_key] = query_embedding
                self._query_embedding_cache.move_to_end(cache_key)
                while len(self._query_embedding_cache) > self._query_embedding_cache_limit:
                    self._query_embedding_cache.popitem(last=False)
        else:
            self._query_embedding_cache.move_to_end(cache_key)
        embedding_ms = (perf_counter() - embedding_started) * 1000
        qdrant_started = perf_counter()
        target_results = await asyncio.gather(
            *(
                self._query_target(
                    target=target,
                    dense_query=query_embedding.dense,
                    sparse_query=to_sparse_vector(query_embedding.sparse),
                    candidate_limit=candidate_limit,
                )
                for target in targets
            )
        )
        qdrant_ms = (perf_counter() - qdrant_started) * 1000
        candidates: list[Any] = []
        dense_scores: dict[tuple[str, str], float] = {}
        sparse_scores: dict[tuple[str, str], float] = {}
        for target, (points, target_dense, target_sparse) in zip(
            targets, target_results, strict=True
        ):
            candidates.extend(points)
            dense_scores.update(
                {(target.collection_name, point_id): score for point_id, score in target_dense.items()}
            )
            sparse_scores.update(
                {(target.collection_name, point_id): score for point_id, score in target_sparse.items()}
            )
        reranking_started = perf_counter()
        if rerank:
            async with self._reranking_slots:
                reranker_scores = await asyncio.to_thread(
                    self.reranker.score,
                    query,
                    [str((point.payload or {}).get("text", ""))[:6000] for point in candidates],
                )
            reranking_ms = (perf_counter() - reranking_started) * 1000
        else:
            reranker_scores = [float(point.score) for point in candidates]
            reranking_ms = 0.0
        hits = [
            RetrievalHit(
                point_id=str(point.id),
                payload=dict(point.payload or {}),
                dense_score=dense_scores.get(
                    (str((point.payload or {}).get("collection_name")), str(point.id))
                ),
                sparse_score=sparse_scores.get(
                    (str((point.payload or {}).get("collection_name")), str(point.id))
                ),
                fused_score=float(point.score),
                reranker_score=reranker_score,
            )
            for point, reranker_score in zip(candidates, reranker_scores, strict=True)
        ]
        hits.sort(key=lambda hit: hit.reranker_score, reverse=True)
        timings = RetrievalTimings(
            embedding_ms=round(embedding_ms, 2),
            qdrant_ms=round(qdrant_ms, 2),
            reranking_ms=round(reranking_ms, 2),
            total_ms=round((perf_counter() - started) * 1000, 2),
            embedding_cache_hit=embedding_cache_hit,
        )
        return hits[:result_limit], timings
