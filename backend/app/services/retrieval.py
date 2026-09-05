from __future__ import annotations

import asyncio
import gc
import hashlib
import re
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from time import perf_counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.core.config import settings
from app.core.qdrant import create_qdrant_client
from app.ingestion.embedder import BGEM3Embedder, resolve_embedding_device
from app.ingestion.init_qdrant import (
    ADVOCATE_CASE_DATA,
    GLOBAL_LEGAL_CORPUS,
    POLICE_CASE_DATA,
)
from app.ingestion.supersession import replacement_for
from app.ingestion.sparse import to_sparse_vector
from app.services.legal_term_normalization import LEGAL_ACRONYM_EXPANSIONS


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
    # Excludes replaced authorities in the query rather than after ranking,
    # so a superseded provision cannot occupy a candidate slot.
    exclude_superseded: bool = False
    corpus_tiers: list[str] = field(default_factory=lambda: ["gold", "extended"])
    case_ids: list[str] = field(default_factory=list)

    def to_qdrant(self) -> models.Filter | None:
        conditions: list[models.Condition] = []
        must_not: list[models.Condition] = []
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
        if self.exclude_superseded:
            # must_not True, rather than must False. The field is tri-state in
            # practice -- True, False, or absent on any index built before it
            # existed -- and matching False excluded every point in the live
            # collection, where all 25,517 hold None. Excluding only an
            # explicit True keeps the filter meaning "not known to be
            # superseded", which is what the caller asked for.
            must_not.append(
                models.FieldCondition(
                    key="is_superseded", match=models.MatchValue(value=True)
                )
            )
        if not conditions and not must_not:
            return None
        return models.Filter(must=conditions or None, must_not=must_not or None)

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
    candidate_count: int = 0
    raw_candidate_count: int = 0
    deduplicated_candidate_count: int = 0
    duplicate_candidate_count: int = 0
    result_count: int = 0
    reranker_input_chunk_count: int = 0
    reranker_input_characters: int = 0
    reranker_input_utf8_bytes: int = 0
    reranker_query_characters_per_pair: int = 0
    reranker_query_utf8_bytes_per_pair: int = 0
    reranker_pair_input_characters: int = 0
    reranker_pair_input_utf8_bytes: int = 0
    reranker_max_length: int | None = None
    lexical_term_document_counts: dict[str, int] = field(default_factory=dict)
    lexical_distinctive_terms: list[str] = field(default_factory=list)
    excluded_candidate_count: int = 0
    scored_candidate_ids: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class RetrievalTarget:
    collection_name: str
    filters: RetrievalFilters


# Legal chunks average ~4,000 characters; this keeps the part that decides
# relevance and drops the tail that only adds reranking cost. Reranking cost
# grows worse than linearly with total input -- 45k characters measured 6.5s
# and 81k measured 18.4s -- so the budget stays.
RERANKER_INPUT_CHARACTERS = 2500


def reranker_excerpt(text: str, query: str, *, budget: int = RERANKER_INPUT_CHARACTERS) -> str:
    """The part of a chunk worth showing the cross-encoder.

    Taking the first `budget` characters spends the budget on wherever the
    chunk happens to start. 27.4% of chunks exceed it, losing 1,830 characters
    on average, and always the tail -- so for a quarter of candidates the
    cross-encoder scores an opening that may have nothing to do with the
    question. Chunks that begin on a Gazette masthead or a heading are scored
    almost entirely on furniture.

    So centre the window on the query instead: score fixed-size windows by how
    many distinct query terms they contain, and return the best one on a
    sentence-ish boundary. Ties keep the earliest window, which preserves
    today's behaviour for chunks where the opening really is the relevant part.
    """
    if len(text) <= budget:
        return text

    terms = {
        term
        for term in re.findall(r"[a-z0-9]{3,}", query.casefold())
        if term not in _EXCERPT_STOPWORDS
    }
    if not terms:
        return text[:budget]

    stride = max(budget // 4, 1)
    folded = text.casefold()
    final_start = max(len(text) - budget, 0)
    # The final window has to be an explicit candidate. With a fixed stride it
    # is generated only when the chunk length happens to be a multiple of the
    # stride, so the end of a chunk -- the part the front-truncation was losing
    # in the first place -- was unreachable for most lengths.
    starts = sorted({*range(0, final_start + 1, stride), final_start})
    best_start, best_score = 0, -1
    for start in starts:
        window = folded[start : start + budget]
        score = sum(1 for term in terms if term in window)
        if score > best_score:
            best_start, best_score = start, score
    if best_score <= 0:
        return text[:budget]

    # Nudge to a boundary so the excerpt does not open mid-word.
    if best_start > 0:
        for separator in (". ", "\n", " "):
            found = text.find(separator, best_start, best_start + 200)
            if found != -1:
                best_start = found + len(separator)
                break
    return text[best_start : best_start + budget]


# Deliberately small: this decides where to point a window, not what a query
# means, and over-filtering here would make every window score zero.
_EXCERPT_STOPWORDS = frozenset(
    {
        "and", "any", "are", "can", "does", "for", "from", "how", "its",
        "may", "not", "the", "that", "this", "under", "was", "what", "when",
        "which", "who", "why", "will", "with", "you", "your",
    }
)


def _base_forms(term: str) -> tuple[str, ...]:
    """Cheap morphological variants of a query term.

    Not a stemmer. It exists to answer one question: is this term rare because
    the corpus does not discuss the topic, or rare because the corpus spells it
    differently? "protections" appears in 35 chunks and "protection" in
    thousands -- the topic is amply covered, and requiring the plural rejected
    every correct passage about the protection of children.
    """
    lowered = term.casefold()
    if len(lowered) < 4:
        return ()
    if lowered.endswith("ies"):
        return (lowered[:-3] + "y",)
    # "-es" drops only after a sibilant, where English adds it to make the
    # plural pronounceable: witnesses, taxes, churches. Applying it generally
    # turns "offences" into "offenc", a string the corpus never contains.
    if lowered.endswith("es") and lowered[:-2].endswith(("s", "x", "z", "ch", "sh")):
        return (lowered[:-2],)
    if lowered.endswith("s") and not lowered.endswith("ss"):
        return (lowered[:-1],)
    return ()


# Collections holding one matter's private evidence. A query against these
# without a case scope returns every matter in them.
CASE_SCOPED_COLLECTIONS = frozenset({POLICE_CASE_DATA, ADVOCATE_CASE_DATA})


def _assert_case_scoped(targets: list[RetrievalTarget]) -> None:
    """Refuse a private-corpus query that names no case.

    `RetrievalFilters.case_ids` is applied only when it is non-empty, which is
    the right behaviour for the public corpus and a disclosure for a private
    one: an empty list there does not mean "this case", it means "every case".

    Every call site today sets it. That is the point -- the isolation is
    currently held by three call sites all remembering, and police and advocate
    are about to add more. Convention is the wrong mechanism for the boundary
    between one investigation's evidence and another's, so it fails here
    instead of returning someone else's material.
    """
    for target in targets:
        if target.collection_name not in CASE_SCOPED_COLLECTIONS:
            continue
        if not target.filters.case_ids:
            raise ValueError(
                f"{target.collection_name!r} holds private case evidence and was "
                "queried with no case_ids. An empty case filter is not applied, "
                "so this would have returned every matter in the collection."
            )


def _prefer_law_in_force(hits: list[RetrievalHit]) -> list[RetrievalHit]:
    """Order by relevance, with a repealed provision giving way to a live one.

    The corpus holds 5,387 chunks of the Indian Penal Code, the Code of
    Criminal Procedure and the Indian Evidence Act against 1,026 of the
    Sanhitas that replaced them on 1 July 2024. Retrieval is volume-sensitive,
    so the repealed provision wins on weight of material: measured per topic,
    "arrest without warrant" is 48 CrPC chunks to 23 BNSS.

    The preference is a rank penalty rather than a score multiplier because the
    ordering key is an RRF score in one lane and a cross-encoder logit in the
    other. It is also deliberately mild: a repealed provision that is markedly
    the better match still wins, because the old codes still govern conduct
    from before the repeal and are sometimes the right answer.

    Repeal is derived from the Act's name rather than read from the payload, so
    this works against an index built before the field existed.
    """
    penalty = settings.repealed_rank_penalty
    if penalty <= 0:
        return sorted(hits, key=lambda hit: hit.reranker_score, reverse=True)

    ordered = sorted(hits, key=lambda hit: hit.reranker_score, reverse=True)

    def effective_rank(position_and_hit: tuple[int, RetrievalHit]) -> int:
        position, hit = position_and_hit
        payload = hit.payload or {}
        repealed = bool(payload.get("replaced_by")) or bool(
            replacement_for(payload.get("act_name"), payload.get("title"))
        )
        return position + (penalty if repealed else 0)

    return [
        hit
        for _, hit in sorted(enumerate(ordered), key=effective_rank)
    ]


def _distinctive_from_counts(counts: dict[str, int]) -> list[str]:
    """Which of a query's terms are rare enough to be required.

    A term absent from the corpus is the strongest possible signal that the
    question is outside it, so when any term has zero matches those alone are
    required. Otherwise the rarest band is required: the cutoff sits a little
    above the minimum so a near-tie does not depend on which of two equally
    rare words happened to be rarer.
    """
    if not counts:
        return []
    zero_frequency = sorted(term for term, count in counts.items() if count == 0)
    if zero_frequency:
        return zero_frequency
    minimum = min(counts.values())
    cutoff = max(minimum, int(minimum * 1.35))
    return sorted(term for term, count in counts.items() if count <= cutoff)


class BGEReranker:
    # bge-reranker-v2-m3 supports an 8192-token context. Using that full context
    # prevents the current 700-word legal chunks from being silently cut down to
    # FlagEmbedding's much smaller default. Eight was the best measured CPU batch
    # for the dominant 40-candidate fallback without changing score output.
    MAX_LENGTH = 8192
    BATCH_SIZE = 8

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
    CANDIDATE_OVERSAMPLE_FACTOR = 3
    NEAR_DUPLICATE_SIMILARITY_THRESHOLD = 0.88
    NEAR_DUPLICATE_SHINGLE_SIZE = 5

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
        self._embedding_executor = ThreadPoolExecutor(
            max_workers=inference_concurrency,
            thread_name_prefix="legal-rag-embedding",
        )
        self._reranking_executor = ThreadPoolExecutor(
            max_workers=inference_concurrency,
            thread_name_prefix="legal-rag-reranker",
        )
        self._query_embedding_cache: OrderedDict[str, Any] = OrderedDict()
        self._query_embedding_cache_limit = settings.query_embedding_cache_size
        # Interactive requests arriving together are encoded as one BGE batch.
        # Without this coalescing, three simultaneous Fast requests queue three
        # separate model passes and the last request absorbs all preceding
        # embedding latency.
        self._query_batch_lock = asyncio.Lock()
        self._pending_query_embeddings: list[
            tuple[str, asyncio.Future[Any]]
        ] = []
        self._query_batch_task: asyncio.Task[None] | None = None
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
        if self._query_batch_task is not None:
            self._query_batch_task.cancel()
        # BGEM3Embedder has no public lifecycle API. It is application-owned here,
        # so releasing its lazy model on shutdown is safe and avoids retaining
        # accelerator memory during graceful worker replacement.
        if isinstance(self.embedder, BGEM3Embedder):
            self.embedder._model = None
        self._embedding_executor.shutdown(wait=True, cancel_futures=True)
        self._reranking_executor.shutdown(wait=True, cancel_futures=True)
        gc.collect()

    async def _run_embedding(self, texts: list[str], *, batch_size: int) -> list[Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._embedding_executor,
            partial(self.embedder.embed_texts, texts, batch_size=batch_size),
        )

    async def _embed_query_batched(self, query: str) -> Any:
        """Coalesce near-simultaneous query embeddings into one model pass."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        async with self._query_batch_lock:
            self._pending_query_embeddings.append((query, future))
            if self._query_batch_task is None or self._query_batch_task.done():
                self._query_batch_task = asyncio.create_task(
                    self._flush_query_embedding_batch()
                )
        return await future

    async def _flush_query_embedding_batch(self) -> None:
        # A very small window captures a burst from concurrent HTTP requests
        # while remaining negligible for a single interactive query.
        await asyncio.sleep(0.01)
        async with self._query_batch_lock:
            pending = self._pending_query_embeddings
            self._pending_query_embeddings = []
        if not pending:
            return
        try:
            async with self._embedding_slots:
                embeddings = await self._run_embedding(
                    [query for query, _ in pending],
                    batch_size=min(len(pending), 8),
                )
            if len(embeddings) != len(pending):
                raise RuntimeError("query embedding batch returned an unexpected size")
            for (_, future), embedding in zip(pending, embeddings, strict=True):
                if not future.done():
                    future.set_result(embedding)
        except BaseException as exc:
            for _, future in pending:
                if not future.done():
                    future.set_exception(exc)

    async def embed_documents(
        self, texts: list[str], *, batch_size: int = 8
    ) -> list[Any]:
        """Reuse the application-owned embedder without concurrent model access."""
        if self._closed:
            raise RuntimeError("retrieval service is closed")
        async with self._embedding_slots:
            return await self._run_embedding(texts, batch_size=batch_size)

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
        lexical_only: bool = False,
        lexical_terms: set[str] | None = None,
        reference_sections: set[str] | None = None,
        exclude_candidate_ids: set[tuple[str, str]] | None = None,
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
            lexical_only=lexical_only,
            lexical_terms=lexical_terms,
            reference_sections=reference_sections,
            exclude_candidate_ids=exclude_candidate_ids,
        )

    async def _search_lexical_target(
        self,
        *,
        target: RetrievalTarget,
        terms: set[str],
        candidate_limit: int,
        result_limit: int,
        reference_sections: set[str] | None = None,
    ) -> tuple[list[RetrievalHit], RetrievalTimings]:
        started = perf_counter()
        query_filter = target.filters.to_qdrant()
        base_conditions = list(query_filter.must or []) if query_filter else []

        async def matching_points(term: str) -> tuple[str, list[Any], int]:
            term_filter = models.Filter(
                must=[
                    *base_conditions,
                    models.FieldCondition(
                        key="text",
                        match=models.MatchText(text=term),
                    ),
                ]
            )
            points_result, count_result = await asyncio.gather(
                self.client.scroll(
                collection_name=target.collection_name,
                scroll_filter=term_filter,
                # Full-text matches are unranked within a scroll page. Fetch a
                # bounded wider pool per term, then rank by whole-query lexical
                # coverage below so an arbitrary first page does not discard
                # the passage that matches several terms.
                limit=max(candidate_limit, 32),
                with_payload=True,
                with_vectors=False,
                ),
                self.client.count(
                    collection_name=target.collection_name,
                    count_filter=term_filter,
                    exact=True,
                ),
            )
            points, _ = points_result
            return term, list(points), int(count_result.count)

        async def points_for_section(section: str, topic_terms: list[str]) -> list[Any]:
            """Fetch a provision by its section number directly.

            A full-text scroll is unranked, so a common word returns an
            arbitrary page of its matches: "equality" matches 242 documents and
            the Constitution's Article 14 was simply not in the 32 that came
            back. Section is an indexed keyword, so asking for it by number is
            both exact and cheap, and it is the only way a question naming a
            provision reliably retrieves that provision.
            """
            # Narrowed by the query's rarest terms. A section number alone is
            # ambiguous - "14" exists in the Prisons Act, the IPC, the Evidence
            # Act and hundreds more - and an unranked scroll would return an
            # arbitrary sixteen of them, which is how the Constitution's
            # Article 14 stayed invisible to a question about equality.
            collected: list[Any] = []
            for term in topic_terms[:2] or [None]:
                conditions = [
                    *base_conditions,
                    models.FieldCondition(
                        key="section", match=models.MatchValue(value=section)
                    ),
                ]
                if term is not None:
                    conditions.append(
                        models.FieldCondition(key="text", match=models.MatchText(text=term))
                    )
                points, _ = await self.client.scroll(
                    collection_name=target.collection_name,
                    scroll_filter=models.Filter(must=conditions),
                    limit=8,
                    with_payload=True,
                    with_vectors=False,
                )
                collected.extend(points)
            return collected

        qdrant_started = perf_counter()
        term_results = await asyncio.gather(
            *(matching_points(term) for term in sorted(terms))
        )
        # The rarest terms carry the topic. Ordering by document frequency here
        # means the section lookup below searches for "equality" rather than
        # "right", which appears in 2,282 documents and selects nothing.
        rarest = [
            term
            for term, _, _ in sorted(term_results, key=lambda item: item[2])
            if not term.isdigit()
        ]
        section_results = await asyncio.gather(
            *(
                points_for_section(section, rarest)
                for section in sorted(reference_sections or ())
            )
        )
        qdrant_ms = (perf_counter() - qdrant_started) * 1000
        term_document_counts = {
            term: count for term, _, count in term_results
        }
        if not term_document_counts:
            # No searchable terms means no lexical evidence, which is an
            # abstention rather than a crash. Validation should prevent this
            # reaching here; a 500 is the wrong failure if it ever does.
            return [], RetrievalTimings(
                embedding_ms=0.0,
                qdrant_ms=qdrant_ms,
                reranking_ms=0.0,
                total_ms=(perf_counter() - started) * 1000,
            )
        distinctive_terms = _distinctive_from_counts(term_document_counts)
        by_id: dict[str, Any] = {}
        match_counts: dict[str, int] = {}
        for points in section_results:
            for point in points:
                by_id[str(point.id)] = point
        for _, points, _ in term_results:
            for point in points:
                point_id = str(point.id)
                by_id[point_id] = point
                match_counts[point_id] = match_counts.get(point_id, 0) + 1
        denominator = max(len(terms), 1)
        coverage_by_id: dict[str, float] = {}
        locally_matched_by_id: dict[str, set[str]] = {}
        for point_id, point in by_id.items():
            payload = dict(point.payload or {})
            title_terms = re.findall(
                r"[a-z0-9]+", str(payload.get("title") or "").casefold()
            )[:40]
            body = " ".join(
                str(payload.get(field) or "")
                for field in ("act_name", "section", "court", "text")
            ).casefold()
            document_terms = [*title_terms, *re.findall(r"[a-z0-9]+", body)]
            window_size = 50
            windows = (
                [document_terms]
                if len(document_terms) <= window_size
                else [
                    document_terms[start : start + window_size]
                    for start in range(0, len(document_terms), window_size // 2)
                ]
            )
            locally_matched_by_id[point_id] = set().union(
                *(terms & set(window) for window in windows)
            )
            coverage_by_id[point_id] = max(
                (len(terms & set(window)) / denominator for window in windows),
                default=0.0,
            )
        hits = [
            RetrievalHit(
                point_id=point_id,
                payload={
                    **dict(point.payload or {}),
                    "collection_name": target.collection_name,
                },
                dense_score=None,
                sparse_score=coverage_by_id[point_id],
                fused_score=coverage_by_id[point_id],
                reranker_score=coverage_by_id[point_id],
            )
            for point_id, point in by_id.items()
        ]
        required_terms = set(distinctive_terms)
        requested_acronyms = terms & LEGAL_ACRONYM_EXPANSIONS.keys()

        def required_legal_entity_match(hit: RetrievalHit) -> bool:
            matched = locally_matched_by_id[hit.point_id]
            for term in required_terms:
                if term in matched:
                    continue
                expansion = set(LEGAL_ACRONYM_EXPANSIONS.get(term, ()))
                if not expansion or not expansion.issubset(matched):
                    return False
            return True

        def named_act_title_match(hit: RetrievalHit) -> bool:
            if not requested_acronyms:
                return False
            title_terms = set(
                re.findall(
                    r"[a-z0-9]+",
                    " ".join(
                        str(hit.payload.get(field) or "")
                        for field in ("title", "act_name")
                    ).casefold(),
                )
            )
            return any(
                set(LEGAL_ACRONYM_EXPANSIONS[acronym]).issubset(title_terms)
                for acronym in requested_acronyms
            )

        requested_sections = {section.casefold() for section in (reference_sections or ())}

        def exact_section_match(hit: RetrievalHit) -> bool:
            """The provision the question actually named.

            Nothing outranks this. Asked about Article 14, the Constitution's
            Article 14 is the answer; it previously lost to any document whose
            source_type happened to be "act", which is how a question about
            equality returned the Model Prison Manual.
            """
            return (
                str(hit.payload.get("section") or "").casefold().strip()
                in requested_sections
                if requested_sections
                else False
            )

        hits.sort(
            key=lambda hit: (
                # A section number alone is ambiguous: "14" exists in the
                # Prisons Act, the IPC, the Evidence Act and 380 other
                # documents. Ranking on it alone buried the Constitution's
                # Article 14 under every unrelated section 14 in the corpus.
                # The provision the question means is the one that matches the
                # number *and* carries the topic word - here, "equality".
                exact_section_match(hit) and required_legal_entity_match(hit),
                exact_section_match(hit),
                required_legal_entity_match(hit),
                named_act_title_match(hit),
                str(hit.payload.get("source_type") or "").casefold() == "act",
                -len(str(hit.payload.get("title") or "")),
                hit.fused_score,
            ),
            reverse=True,
        )
        return hits[:result_limit], RetrievalTimings(
            embedding_ms=0.0,
            qdrant_ms=qdrant_ms,
            reranking_ms=0.0,
            total_ms=(perf_counter() - started) * 1000,
            candidate_count=len(hits),
            result_count=min(len(hits), result_limit),
            lexical_term_document_counts=term_document_counts,
            lexical_distinctive_terms=distinctive_terms,
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
                # Reciprocal Rank Fusion runs server-side. Qdrant does not
                # expose its k constant through this API, so the value is
                # fixed by the pinned Qdrant image rather than by us; see
                # QDRANT_IMAGE_VERSION. Do not bump that image without
                # re-running the retrieval evaluation.
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

    @classmethod
    def _deduplicate_candidates(
        cls,
        candidates: list[Any],
    ) -> list[Any]:
        """Collapse near-identical chunks from one source before reranking.

        Candidates are considered duplicates only when they share a stable
        source-document identifier. This deliberately preserves similar text
        from distinct authorities. Since the fused results arrive in descending
        score order, the first member of each cluster is its highest-scoring
        representative.
        """

        def source_key(point: Any) -> tuple[str, str] | None:
            payload = dict(point.payload or {})
            collection = str(payload.get("collection_name") or "")
            for field_name in (
                "canonical_document_id",
                "document_id",
                "source_id",
            ):
                value = str(payload.get(field_name) or "").strip()
                if value:
                    return collection, value
            return None

        def text_shingles(point: Any) -> set[tuple[str, ...]]:
            words = re.findall(
                r"[a-z0-9]+",
                str((point.payload or {}).get("text") or "").casefold(),
            )
            size = cls.NEAR_DUPLICATE_SHINGLE_SIZE
            if len(words) < size:
                return {tuple(words)} if words else set()
            return {
                tuple(words[index : index + size])
                for index in range(len(words) - size + 1)
            }

        def similarity(left: set[tuple[str, ...]], right: set[tuple[str, ...]]) -> float:
            if not left or not right:
                return 0.0
            return len(left & right) / len(left | right)

        representatives: list[Any] = []
        clusters_by_source: dict[
            tuple[str, str], list[set[tuple[str, ...]]]
        ] = {}
        shingle_cache: dict[int, set[tuple[str, ...]]] = {}
        for point in sorted(candidates, key=lambda item: float(item.score), reverse=True):
            key = source_key(point)
            shingles = shingle_cache.setdefault(id(point), text_shingles(point))
            source_clusters = clusters_by_source.setdefault(key, []) if key else []
            if key and any(
                similarity(shingles, representative) >= cls.NEAR_DUPLICATE_SIMILARITY_THRESHOLD
                for representative in source_clusters
            ):
                continue
            representatives.append(point)
            if key:
                source_clusters.append(shingles)
        return representatives

    async def distinctive_query_terms(
        self,
        terms: set[str],
        *,
        target: RetrievalTarget,
    ) -> tuple[dict[str, int], list[str]]:
        """The query terms rare enough to carry its topic.

        This used to be computed only inside the lexical path, so when the Fast
        lane moved to dense+sparse RRF it silently stopped being computed at
        all: `_mandatory_focus_match` was handed an empty set, which it treats
        as "nothing required", leaving an unweighted coverage floor as the only
        gate. A question whose defining word is absent from the corpus could
        then be answered by a passage sharing its filler words -- exactly the
        abstention failure measured against the golden set.

        Frequencies come from the collection being searched, so the notion of
        "rare" follows the corpus rather than a hardcoded list.
        """
        cleaned = {term.casefold().strip() for term in terms if term.strip()}
        cleaned = {term for term in cleaned if len(term) > 1}
        if not cleaned:
            return {}, []

        base = target.filters.to_qdrant()
        base_conditions = list(base.must or []) if base else []

        async def count_for(term: str) -> tuple[str, int]:
            result = await self.client.count(
                collection_name=target.collection_name,
                count_filter=models.Filter(
                    must=[
                        *base_conditions,
                        models.FieldCondition(key="text", match=models.MatchText(text=term)),
                    ]
                ),
                exact=True,
            )
            return term, int(result.count)

        # A term's effective frequency is the highest among its spellings, so a
        # rare inflection of a well-covered topic is not mistaken for a gap.
        wanted: dict[str, tuple[str, ...]] = {
            term: (term, *_base_forms(term)) for term in sorted(cleaned)
        }
        lookups = sorted({form for forms in wanted.values() for form in forms})
        raw = dict(await asyncio.gather(*(count_for(form) for form in lookups)))
        counts = {
            term: max(raw.get(form, 0) for form in forms)
            for term, forms in wanted.items()
        }
        return counts, _distinctive_from_counts(counts)

    async def search_across_collections_with_timings(
        self,
        query: str,
        *,
        targets: list[RetrievalTarget],
        candidate_limit: int = 20,
        result_limit: int = 5,
        rerank: bool = True,
        lexical_only: bool = False,
        lexical_terms: set[str] | None = None,
        reference_sections: set[str] | None = None,
        exclude_candidate_ids: set[tuple[str, str]] | None = None,
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
        _assert_case_scoped(targets)
        # A caller asking for reranking gets it only where it is switched on.
        # Callers that never wanted it are unaffected.
        rerank = rerank and settings.cross_encoder_reranking_enabled
        if lexical_only:
            if len(targets) != 1:
                raise ValueError("lexical-only retrieval supports exactly one collection")
            terms = {term.casefold().strip() for term in (lexical_terms or set()) if term.strip()}
            if not terms:
                terms = {term for term in query.casefold().split() if len(term) > 1}
            return await self._search_lexical_target(
                target=targets[0],
                terms=terms,
                candidate_limit=candidate_limit,
                result_limit=result_limit,
                reference_sections=reference_sections,
            )

        started = perf_counter()
        embedding_started = perf_counter()
        # The model identity is part of the key. Two models produce vectors in
        # different spaces, so a cache keyed on query text alone would serve a
        # stale-space vector after a model or dimension change.
        cache_key = hashlib.sha256(
            "\x00".join(
                (
                    settings.embedding_model,
                    str(settings.embedding_dimension),
                    " ".join(query.casefold().split()),
                )
            ).encode("utf-8")
        ).hexdigest()
        query_embedding = self._query_embedding_cache.get(cache_key)
        embedding_cache_hit = query_embedding is not None
        if query_embedding is None:
            query_embedding = await self._embed_query_batched(query)
            if self._query_embedding_cache_limit:
                self._query_embedding_cache[cache_key] = query_embedding
                self._query_embedding_cache.move_to_end(cache_key)
                while len(self._query_embedding_cache) > self._query_embedding_cache_limit:
                    self._query_embedding_cache.popitem(last=False)
        else:
            self._query_embedding_cache.move_to_end(cache_key)
        embedding_ms = (perf_counter() - embedding_started) * 1000
        qdrant_started = perf_counter()
        raw_candidate_limit = (
            candidate_limit * self.CANDIDATE_OVERSAMPLE_FACTOR
            if rerank
            else candidate_limit
        )
        target_results = await asyncio.gather(
            *(
                self._query_target(
                    target=target,
                    dense_query=query_embedding.dense,
                    sparse_query=to_sparse_vector(query_embedding.sparse),
                    candidate_limit=raw_candidate_limit,
                )
                for target in targets
            )
        )
        qdrant_ms = (perf_counter() - qdrant_started) * 1000
        candidates: list[Any] = []
        raw_candidate_count = 0
        duplicate_candidate_count = 0
        excluded_candidate_count = 0
        excluded_identities = exclude_candidate_ids or set()
        dense_scores: dict[tuple[str, str], float] = {}
        sparse_scores: dict[tuple[str, str], float] = {}
        for target, (points, target_dense, target_sparse) in zip(
            targets, target_results, strict=True
        ):
            raw_candidate_count += len(points)
            if rerank:
                deduplicated = self._deduplicate_candidates(list(points))
                duplicate_candidate_count += len(points) - len(deduplicated)
                selected_candidates = deduplicated[:candidate_limit]
                eligible_candidates = [
                    point
                    for point in selected_candidates
                    if (target.collection_name, str(point.id)) not in excluded_identities
                ]
                excluded_candidate_count += len(selected_candidates) - len(
                    eligible_candidates
                )
                candidates.extend(eligible_candidates)
            else:
                candidates.extend(points)
            dense_scores.update(
                {(target.collection_name, point_id): score for point_id, score in target_dense.items()}
            )
            sparse_scores.update(
                {(target.collection_name, point_id): score for point_id, score in target_sparse.items()}
            )
        # The cross-encoder judges relevance, which the opening of a legal
        # passage establishes; it does not need the whole provision, which the
        # reasoning stage reads in full afterwards. Cost grows worse than
        # linearly with total input - 45k characters measured 6.5s and 81k
        # measured 18.4s - so this is the cheapest second in the pipeline.
        reranker_documents = [
            reranker_excerpt(str((point.payload or {}).get("text", "")), query)
            for point in candidates
        ]
        reranking_started = perf_counter()
        if rerank:
            async with self._reranking_slots:
                reranker_scores = await asyncio.get_running_loop().run_in_executor(
                    self._reranking_executor,
                    self.reranker.score,
                    query,
                    reranker_documents,
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
        hits = _prefer_law_in_force(hits)
        timings = RetrievalTimings(
            embedding_ms=round(embedding_ms, 2),
            qdrant_ms=round(qdrant_ms, 2),
            reranking_ms=round(reranking_ms, 2),
            total_ms=round((perf_counter() - started) * 1000, 2),
            embedding_cache_hit=embedding_cache_hit,
            candidate_count=len(candidates),
            raw_candidate_count=raw_candidate_count,
            deduplicated_candidate_count=len(candidates),
            duplicate_candidate_count=duplicate_candidate_count,
            result_count=min(len(hits), result_limit),
            reranker_input_chunk_count=len(reranker_documents) if rerank else 0,
            reranker_input_characters=(
                sum(len(document) for document in reranker_documents) if rerank else 0
            ),
            reranker_input_utf8_bytes=(
                sum(len(document.encode("utf-8")) for document in reranker_documents)
                if rerank
                else 0
            ),
            reranker_query_characters_per_pair=len(query) if rerank else 0,
            reranker_query_utf8_bytes_per_pair=(
                len(query.encode("utf-8")) if rerank else 0
            ),
            reranker_pair_input_characters=(
                sum(len(document) + len(query) for document in reranker_documents)
                if rerank
                else 0
            ),
            reranker_pair_input_utf8_bytes=(
                sum(
                    len(document.encode("utf-8")) + len(query.encode("utf-8"))
                    for document in reranker_documents
                )
                if rerank
                else 0
            ),
            reranker_max_length=(
                (int(getattr(self.reranker, "MAX_LENGTH", 0)) or None)
                if rerank
                else None
            ),
            excluded_candidate_count=excluded_candidate_count,
            scored_candidate_ids=[
                (
                    str((point.payload or {}).get("collection_name") or ""),
                    str(point.id),
                )
                for point in candidates
            ],
        )
        return hits[:result_limit], timings
