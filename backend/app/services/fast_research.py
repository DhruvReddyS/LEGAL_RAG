from __future__ import annotations

import asyncio
import re
from time import perf_counter

from app.schemas.agents import AgentCitation, AgentTraceEvent, QueryIntent
from app.core.config import settings
from app.services.generation import INSUFFICIENT_EVIDENCE
from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS
from app.services.retrieval import (
    HybridRetrievalService,
    RetrievalFilters,
    RetrievalTarget,
)
from app.services.legal_term_normalization import (
    LEGAL_ACRONYM_EXPANSIONS,
    normalize_legal_terms,
)


# Function words and words that describe how an answer should be presented.
#
# Two classes were removed. "police", "report", "law" and "legal" are among the
# most discriminative tokens in an Indian legal corpus - they separate an FIR
# procedure from a contract chapter - and stripping them left the citizen
# question "what should I tell police when reporting missing property" with
# almost no anchors. "passages", "statutory", "show", "relevant" and "verified"
# were benchmark phrasing rather than general presentation vocabulary.
FOCUS_STOPWORDS = {
    "a", "an", "and", "any", "are", "be", "can", "do", "does", "for", "from",
    "how", "i", "if", "in", "is", "it", "may", "me", "must", "my", "of", "on",
    "or", "please", "should", "that", "the", "to", "under", "was", "what",
    "when", "which", "who", "why", "will", "with", "you", "your",
    # Presentation vocabulary: how to answer, not what about.
    "explain", "explanation", "language", "plain", "simple", "summarise",
    "summarize", "tell", "understand",
}


# "Article 14", "Section 154", "Order 39 Rule 2" - the highest-signal pattern
# in legal search, and the one that lexical scoring destroys. Scored as loose
# tokens, "article" matches 2,302 documents and "14" matches 2,156, so a
# passage that merely discusses equality outranks the provision itself.
_STATUTORY_REFERENCE_RE = re.compile(
    r"\b(articles?|sections?|rules?|orders?|clauses?|regulations?)\s+"
    r"(\d+[A-Za-z]?)\b",
    re.IGNORECASE,
)

_REFERENCE_SINGULARS = {
    "articles": "article", "sections": "section", "rules": "rule",
    "orders": "order", "clauses": "clause", "regulations": "regulation",
}


def _statutory_references(query: str) -> list[tuple[str, str]]:
    """Extract (kind, number) pairs a passage must actually contain."""
    references: list[tuple[str, str]] = []
    for kind, number in _STATUTORY_REFERENCE_RE.findall(query):
        folded = kind.casefold()
        references.append(
            (_REFERENCE_SINGULARS.get(folded, folded), number.casefold())
        )
    return list(dict.fromkeys(references))


def _mentions_reference(payload: dict, kind: str, number: str) -> bool:
    """Whether the passage cites this provision, as a phrase rather than as
    two independent tokens that happen to co-occur."""
    haystack = " ".join(
        str(payload.get(field) or "")
        for field in ("section", "title", "act_name", "heading_path", "text")
    ).casefold()
    # "article 14", "article-14", "article no. 14", "art. 14"
    pattern = rf"\b{kind[:3]}[a-z]*\.?\s*(?:no\.?\s*)?[-–]?\s*{re.escape(number)}\b"
    if re.search(pattern, haystack):
        return True
    # A section payload naming the number directly is equally decisive.
    return str(payload.get("section") or "").casefold().strip() == number


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

    async def run(
        self,
        *,
        query: str,
        role: str,
        case_id: str | None,
        history: list[dict[str, str]],
    ) -> dict:
        # role and case_id are accepted and deliberately unused: Fast searches
        # the global corpus only. Reading private case evidence here would put
        # it behind a lane that runs no verifier, so scoped retrieval stays a
        # Deep capability. history is unused because Fast resolves no
        # references; a follow-up escalates rather than guessing.
        del role, case_id, history
        started = perf_counter()
        # Typo correction ran in the Deep path only, so "pocos" retrieved
        # nothing in Fast while working correctly one lane over.
        normalization = normalize_legal_terms(query)
        query = normalization.normalized
        focus_tokens = _focus_tokens(query)
        # Dense + sparse with server-side RRF, and no cross-encoder.
        #
        # This lane was lexical-only because the dense path once measured
        # 8,489 ms p95. Warm, and with the reranker input capped, it now
        # measures 126-699 ms - inside the interactive budget with room to
        # spare - and the relevance difference is not marginal. Asked to
        # explain Article 14, the lexical lane returned the Model Prison
        # Manual; RRF returns the Constitution's Article 14 and a Supreme
        # Court judgment construing it.
        #
        # An unranked full-text scroll cannot be fixed by better filtering,
        # which is what several rounds of tuning here established: a common
        # term returns an arbitrary page of its matches, so the right passage
        # is often not a candidate at all. Ranking has to come from the query.
        corpus_filters = RetrievalFilters(corpus_tiers=["gold", "extended"])
        # Run the frequency lookup alongside the search rather than after it.
        # These are Qdrant counts with no embedding step, so concurrently they
        # cost the lane nothing measurable.
        search = self.retrieval.search_with_timings(
            query,
            filters=corpus_filters,
            candidate_limit=max(settings.fast_candidate_limit, 20),
            result_limit=max(settings.fast_candidate_limit, 20),
            rerank=False,
        )
        term_frequencies = self.retrieval.distinctive_query_terms(
            focus_tokens,
            target=RetrievalTarget(
                collection_name=GLOBAL_LEGAL_CORPUS, filters=corpus_filters
            ),
        )
        (hits, retrieval_timings), (_, distinctive) = await asyncio.gather(
            search, term_frequencies
        )
        raw_result_count = len(hits)
        # Computed here rather than taken from the timings. The lexical path
        # populated `lexical_distinctive_terms`; this lane no longer uses that
        # path, so reading it returned an empty set and made the mandatory-term
        # gate below a no-op -- the abstention regression the golden set found.
        distinctive_terms = set(distinctive)
        # RRF has already ranked these, so the coverage gate is a floor against
        # a topically unrelated passage rather than the ranking mechanism it
        # was under lexical search. It is applied only while it leaves
        # something behind: a well-ranked dense hit that shares few surface
        # words with the question is common and usually correct.
        # A hard floor, not a preference. Falling back to the top-ranked hits
        # when nothing clears it would reintroduce the failure this gate exists
        # to prevent: dense retrieval always returns its nearest neighbours, so
        # a question about a missing pet would be answered with missing-child
        # procedure simply because nothing closer exists. Abstaining is the
        # correct answer to a gap in the corpus.
        relevant_hits = [
            hit
            for hit in hits
            if _lexical_coverage(focus_tokens, hit.payload) >= 0.34
            and _mandatory_focus_match(
                distinctive_terms,
                _locally_matched_focus_terms(focus_tokens, hit.payload),
            )
        ]
        # When the question names a provision, a passage that does not cite it
        # is not an answer to that question however well its words overlap.
        references = _statutory_references(query)
        if references:
            cited = [
                hit
                for hit in relevant_hits
                if all(
                    _mentions_reference(hit.payload, kind, number)
                    for kind, number in references
                )
            ]
            # Only narrow when something survives: an unusual provision absent
            # from the corpus should still return its nearest material rather
            # than turning a weak answer into no answer.
            if cited:
                relevant_hits = cited
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
            # Retrieval rank now carries the relevance signal, so confidence
            # reflects how well the returned passages actually cover the
            # question rather than how many mandatory terms survived a gate
            # that no longer decides anything.
            confidence = min(
                0.85, 0.6 * mean_coverage + 0.4 * focus_term_recall
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
                        "legal_term_corrections": [
                            {"from": source, "to": target}
                            for source, target in normalization.corrections
                        ],
                        "lexical_gate": 0.5,
                        "statutory_references": [
                            f"{kind} {number}" for kind, number in _statutory_references(query)
                        ],
                        "reranker_skipped": True,
                        "no_generative_claims": True,
                        "timings_ms": timings,
                    },
                )
            ],
            "timings": timings,
        }
