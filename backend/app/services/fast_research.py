from __future__ import annotations

import re
from time import perf_counter

from app.schemas.agents import AgentCitation, AgentTraceEvent, QueryIntent
from app.core.config import settings
from app.services.generation import INSUFFICIENT_EVIDENCE
from app.services.retrieval import HybridRetrievalService, RetrievalFilters
from app.services.legal_term_normalization import LEGAL_ACRONYM_EXPANSIONS


FOCUS_STOPWORDS = {
    "a", "an", "and", "are", "be", "can", "do", "does", "for", "from", "how", "i",
    "in", "is", "it", "law", "legal", "may", "must", "of", "on", "or", "police",
    "report", "request", "should", "the", "to", "under", "what", "when", "which", "with",
    "address", "details", "disclosed", "facts", "passages", "relevant", "show", "statutory",
    "steps", "verified",
    "explain", "explanation", "language", "plain", "please", "understand",
}


def _compact(value: object, limit: int = 420) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _focus_tokens(query: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", query.casefold())
        if len(token) > 1 and token not in FOCUS_STOPWORDS
    }
    for token in tuple(tokens):
        tokens.update(LEGAL_ACRONYM_EXPANSIONS.get(token, ()))
    return tokens


def _payload_windows(payload: dict) -> list[set[str]]:
    title_tokens = re.findall(r"[a-z0-9]+", str(payload.get("title") or "").casefold())[:40]
    body = " ".join(
        str(payload.get(field) or "")
        for field in ("act_name", "section", "court", "text")
    ).casefold()
    document_tokens = [*title_tokens, *re.findall(r"[a-z0-9]+", body)]
    # Corpus chunks can be long and contain unrelated terms hundreds of words
    # apart. Relevance requires query concepts to co-occur locally, preventing
    # a missing-child or evidence-law passage from matching a missing-pet query
    # merely because both words appear somewhere in the chunk.
    window_size = 50
    if len(document_tokens) <= window_size:
        return [set(document_tokens)]
    return [
        set(document_tokens[start : start + window_size])
        for start in range(0, len(document_tokens), window_size // 2)
    ]


def _lexical_coverage(query_tokens: set[str], payload: dict) -> float:
    if not query_tokens:
        return 1.0
    return max(
        (len(query_tokens & window) / len(query_tokens) for window in _payload_windows(payload)),
        default=0.0,
    )


def _locally_matched_focus_terms(query_tokens: set[str], payload: dict) -> set[str]:
    """Return query terms that occur in at least one local relevance window."""
    matched: set[str] = set()
    for window in _payload_windows(payload):
        matched.update(query_tokens & window)
    return matched


def _mandatory_focus_match(
    mandatory_terms: set[str],
    matched_terms: set[str],
) -> bool:
    for term in mandatory_terms:
        if term in matched_terms:
            continue
        expansion = set(LEGAL_ACRONYM_EXPANSIONS.get(term, ()))
        if not expansion or not expansion.issubset(matched_terms):
            return False
    return True


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
        focus_tokens = _focus_tokens(query)
        hits, retrieval_timings = await self.retrieval.search_with_timings(
            query,
            filters=RetrievalFilters(corpus_tiers=["gold", "extended"]),
            candidate_limit=settings.fast_candidate_limit,
            result_limit=settings.fast_candidate_limit,
            rerank=False,
            lexical_only=True,
            lexical_terms=focus_tokens,
        )
        raw_result_count = len(hits)
        distinctive_terms = set(retrieval_timings.lexical_distinctive_terms)
        relevant_hits = [
            hit
            for hit in hits
            if _lexical_coverage(focus_tokens, hit.payload) >= 0.5
            and _mandatory_focus_match(
                distinctive_terms,
                _locally_matched_focus_terms(focus_tokens, hit.payload),
            )
        ]
        hits = _select_diverse_hits(relevant_hits, settings.fast_result_limit)
        if not hits:
            answer = INSUFFICIENT_EVIDENCE
            citations: list[AgentCitation] = []
            confidence = 0.0
            strength = "insufficient"
        else:
            citations = []
            lines = [
                "Fast evidence brief — the following governed corpus passages are the closest authorities located. "
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
                    # Fast mode performs retrieval only. It has not run the
                    # claim/source verifier used by Deep Review.
                    verification_status="unverified",
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
            coverage_scores = [_lexical_coverage(focus_tokens, hit.payload) for hit in hits]
            matched_focus_terms = set().union(
                *(
                    _locally_matched_focus_terms(focus_tokens, hit.payload)
                    for hit in hits
                )
            )
            focus_term_recall = (
                len(matched_focus_terms) / len(focus_tokens) if focus_tokens else 0.0
            )
            mandatory_term_match_rate = (
                sum(
                    _mandatory_focus_match(
                        distinctive_terms,
                        _locally_matched_focus_terms(focus_tokens, hit.payload),
                    )
                    for hit in hits
                )
                / len(hits)
            )
            mean_coverage = sum(coverage_scores) / len(coverage_scores)
            # Coverage and recall overlap, so multiplying them double-penalises
            # a passage for the same missing generic query word. A weighted
            # relevance score keeps the mandatory legal term as a hard factor
            # while measuring breadth without using document count.
            confidence = min(
                0.85,
                (0.7 * mean_coverage + 0.3 * focus_term_recall)
                * mandatory_term_match_rate,
            )
            strength = (
                "strong"
                if confidence >= 0.75
                else "moderate"
                if confidence >= settings.fast_auto_escalation_threshold
                else "insufficient"
            )

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
                        "mean_local_coverage": mean_coverage if hits else 0.0,
                        "focus_term_recall": focus_term_recall if hits else 0.0,
                        "mandatory_term_match_rate": mandatory_term_match_rate if hits else 0.0,
                        "distinctive_terms": sorted(distinctive_terms),
                        "term_document_counts": retrieval_timings.lexical_term_document_counts,
                        "confidence_method": "weighted_coverage_recall_x_mandatory_term_match_rate",
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
