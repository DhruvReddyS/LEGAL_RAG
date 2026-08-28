from __future__ import annotations

import re
from time import perf_counter

from app.schemas.agents import AgentCitation, AgentTraceEvent, QueryIntent
from app.core.config import settings
from app.services.generation import INSUFFICIENT_EVIDENCE
from app.services.retrieval import HybridRetrievalService, RetrievalFilters


FOCUS_STOPWORDS = {
    "a", "an", "and", "are", "be", "can", "do", "does", "for", "from", "how", "i",
    "in", "is", "it", "law", "legal", "may", "must", "of", "on", "or", "police",
    "report", "request", "should", "the", "to", "under", "what", "when", "which", "with",
}


def _compact(value: object, limit: int = 420) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _focus_tokens(query: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", query.casefold())
        if len(token) > 1 and token not in FOCUS_STOPWORDS
    }


def _lexical_coverage(query_tokens: set[str], payload: dict) -> float:
    if not query_tokens:
        return 1.0
    searchable = " ".join(
        str(payload.get(field) or "")
        for field in ("title", "act_name", "section", "court", "text")
    ).casefold()
    document_tokens = set(re.findall(r"[a-z0-9]+", searchable))
    return len(query_tokens & document_tokens) / len(query_tokens)


def _document_key(hit: object) -> str:
    payload = getattr(hit, "payload")
    stable_identity = (
        payload.get("canonical_document_id")
        or payload.get("document_id")
        or payload.get("source_url")
        or payload.get("title")
    )
    if stable_identity:
        return " ".join(str(stable_identity).casefold().split())
    return str(getattr(hit, "point_id"))


def _select_diverse_hits(hits: list, limit: int) -> list:
    """Return the best passage from each distinct authority, without padding duplicates."""
    selected: list = []
    seen_documents: set[str] = set()
    for hit in hits:
        document_key = _document_key(hit)
        if document_key in seen_documents:
            continue
        selected.append(hit)
        seen_documents.add(document_key)
        if len(selected) == limit:
            return selected
    return selected


class FastLegalResearchService:
    """Retrieval-first legal evidence brief with no generative claims.

    Fast mode deliberately skips the cross-encoder and LLM chain. It exposes
    high-ranking Gold passages as a reviewable evidence brief, making its speed
    and its narrower capability explicit instead of pretending that an
    unverified model completion is a legal conclusion.
    """

    def __init__(self, retrieval: HybridRetrievalService) -> None:
        self.retrieval = retrieval

    async def run(self, *, query: str, role: str, case_id: str | None, history: list[dict[str, str]]) -> dict:
        del role, case_id, history
        started = perf_counter()
        hits, retrieval_timings = await self.retrieval.search_with_timings(
            query,
            filters=RetrievalFilters(corpus_tiers=["gold", "extended"]),
            candidate_limit=settings.fast_candidate_limit,
            result_limit=settings.fast_candidate_limit,
            rerank=False,
        )
        focus_tokens = _focus_tokens(query)
        raw_result_count = len(hits)
        relevant_hits = [hit for hit in hits if _lexical_coverage(focus_tokens, hit.payload) >= 0.5]
        hits = _select_diverse_hits(relevant_hits, settings.fast_result_limit)
        if not hits:
            answer = INSUFFICIENT_EVIDENCE
            citations: list[AgentCitation] = []
            confidence = 0.0
            strength = "insufficient"
        else:
            citations = []
            lines = [
                "Fast evidence brief — the following verified corpus passages are the closest authorities located. "
                "This mode prioritises source inspection and does not synthesise a final legal opinion."
            ]
            for number, hit in enumerate(hits, 1):
                payload = hit.payload
                citation = AgentCitation(
                    number=number,
                    chunk_id=str(payload.get("chunk_id") or hit.point_id),
                    title=str(payload.get("title") or "Unknown source"),
                    source_type=str(payload.get("source_type") or "unknown"),
                    page_start=int(payload.get("page_start") or 1),
                    page_end=int(payload.get("page_end") or payload.get("page_start") or 1),
                    court=payload.get("court") or None,
                    act_name=payload.get("act_name") or None,
                    section=payload.get("section") or None,
                    source_url=payload.get("source_url") or None,
                    excerpt=_compact(payload.get("text"), 900),
                    retrieval_score=hit.reranker_score,
                    verification_status="verified",
                    current_status=(
                        "current"
                        if payload.get("is_current") is True
                        else "superseded"
                        if payload.get("is_superseded") is True
                        else "status_unverified"
                    ),
                )
                citations.append(citation)
                descriptor = citation.act_name or citation.court or citation.source_type.replace("_", " ")
                section = f", section {citation.section}" if citation.section else ""
                lines.append(
                    f"{number}. {citation.title} ({descriptor}{section}, pages {citation.page_start}–{citation.page_end}): "
                    f"{_compact(payload.get('text'))} [Source {number}]"
                )
            if any(hit.payload.get("is_current") is not True for hit in hits):
                lines.append(
                    "Currency notice: one or more retrieved records are not marked as current. Confirm amendments, "
                    "commencement and repeal status before relying on them."
                )
            answer = "\n\n".join(lines)
            unique_documents = len({str(hit.payload.get("canonical_document_id") or hit.point_id) for hit in hits})
            confidence = min(0.78, 0.48 + 0.08 * unique_documents)
            strength = "moderate" if unique_documents >= 2 else "insufficient"

        total_ms = round((perf_counter() - started) * 1000, 2)
        timings = {
            "embedding_ms": retrieval_timings.embedding_ms,
            "qdrant_ms": retrieval_timings.qdrant_ms,
            "reranking_ms": retrieval_timings.reranking_ms,
            "retrieval_total_ms": retrieval_timings.total_ms,
            "embedding_cache_hit": retrieval_timings.embedding_cache_hit,
            "workflow_total_ms": total_ms,
        }
        intent = QueryIntent(
            intent="fast_evidence_research",
            entities=[],
            language="English",
            complexity="simple",
            retrieval_query=query,
        )
        return {
            "final_answer": answer,
            "citations": citations,
            "confidence_score": confidence,
            "evidence_strength": strength,
            "intent": intent,
            "agent_trace": [
                AgentTraceEvent(
                    node="fast_retrieval",
                    details={
                        "result_count": len(hits),
                        "raw_result_count": raw_result_count,
                        "relevant_result_count": len(relevant_hits),
                        "unique_document_count": len({_document_key(hit) for hit in hits}),
                        "diversity_selection": True,
                        "focus_tokens": sorted(focus_tokens),
                        "lexical_gate": 0.5,
                        "reranker_skipped": True,
                        "no_generative_claims": True,
                        "timings_ms": timings,
                    },
                )
            ],
            "timings": timings,
        }
