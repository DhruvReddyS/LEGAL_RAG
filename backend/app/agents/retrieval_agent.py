from __future__ import annotations

from time import perf_counter_ns

from app.schemas.agents import AgentTraceEvent
from app.services.retrieval import HybridRetrievalService, RetrievalFilters
from app.services.retrieval import RetrievalTarget
from app.services.fast_research import (
    _focus_tokens,
    _payload_windows,
)
from app.ingestion.init_qdrant import ADVOCATE_CASE_DATA, GLOBAL_LEGAL_CORPUS, POLICE_CASE_DATA
from app.core.config import settings
from app.services.pipeline_telemetry import append_stage_metric, text_size


LOW_RERANKER_SCORE_FALLBACK_THRESHOLD = 0.15
TOPIC_ANCHOR_MIN_COVERAGE = 0.5
LOW_SCORE_FALLBACK_TERMS = (
    "non-cognizable offence General Diary entry SOP complaint procedure"
)
PROCEDURE_ANCHOR_TERMS = (
    "complaint",
    "procedure",
    "injunction",
    "magistrate",
    "officer",
    "report",
    "fir",
    "general diary",
)


def _reported_timings(timings: object) -> dict:
    return {
        key: value
        for key, value in vars(timings).items()
        if key != "scored_candidate_ids"
    }


def _anchor_stem(token: str) -> str:
    """Normalize only common inflections for lexical anchor comparison."""
    if len(token) > 4 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-1]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def _topic_anchor_details(query: str, payload: dict) -> tuple[set[str], set[str], float]:
    focus_tokens = _focus_tokens(query)
    if not focus_tokens:
        return focus_tokens, set(), 1.0
    focus_stems = {token: _anchor_stem(token) for token in focus_tokens}
    best_matches: set[str] = set()
    for window in _payload_windows(payload):
        window_stems = {_anchor_stem(token) for token in window}
        matches = {
            token for token, stem in focus_stems.items() if stem in window_stems
        }
        if len(matches) > len(best_matches):
            best_matches = matches
    return focus_tokens, best_matches, len(best_matches) / len(focus_tokens)


async def retrieval_node(state: dict, service: HybridRetrievalService) -> dict:
    started_ns = perf_counter_ns()
    retry_count = int(state.get("retry_count", 0))
    # The topic query is the normalized question itself, never an expanded
    # form. Retrieval writes its expansions back into state["retrieval_query"],
    # so deriving the retry query from that compounded fallback terms across
    # passes and drifted further from the user's topic each time. It is also
    # the correct reference for the anchor check: "governing law authoritative
    # provision" is search scaffolding, not part of what the user asked about.
    intent = state.get("intent")
    topic_query = str(
        getattr(intent, "retrieval_query", None) or state.get("query") or ""
    )
    query = topic_query or str(state.get("retrieval_query") or state["query"])
    if retry_count:
        entities = ", ".join(state["intent"].entities)
        # Preserve query-understanding normalization on every retry. Rebuilding
        # from raw user text here previously reintroduced corrected typos.
        query = f"{query} {entities} governing law authoritative provision".strip()
    case_id = state.get("case_id")
    role = str(state.get("role") or "citizen")
    targets = [
        RetrievalTarget(
            collection_name=GLOBAL_LEGAL_CORPUS,
            filters=RetrievalFilters(corpus_tiers=["gold", "extended"]),
        )
    ]
    if case_id and role in {"police", "advocate"}:
        targets.append(
            RetrievalTarget(
                collection_name=POLICE_CASE_DATA if role == "police" else ADVOCATE_CASE_DATA,
                filters=RetrievalFilters(corpus_tiers=[], case_ids=[str(case_id)]),
            )
        )
    try:
        hits, timings = await service.search_across_collections_with_timings(
            query,
            targets=targets,
            candidate_limit=40 if retry_count else 20,
            result_limit=8 if retry_count else 5,
        )
        initial_query = query
        initial_hits = hits
        initial_timings = timings
        initial_max_score = max(
            (hit.reranker_score for hit in initial_hits),
            default=0.0,
        )
        top_hit = max(
            initial_hits,
            key=lambda hit: hit.reranker_score,
            default=None,
        )
        focus_tokens, top_matched_anchor_terms, top_anchor_coverage = (
            _topic_anchor_details(topic_query, top_hit.payload)
            if top_hit is not None
            else (_focus_tokens(topic_query), set(), 0.0)
        )
        top_has_topic_anchor = (
            bool(top_hit)
            and top_anchor_coverage >= TOPIC_ANCHOR_MIN_COVERAGE
        )
        # The gate applies on every pass. Restricting it to the first pass left
        # the retry with no relevance floor at all, which is the pass most
        # likely to drift: it searches a broadened query after verification has
        # already rejected the first answer.
        # The 0.15 threshold is calibrated for cross-encoder output. Fused RRF
        # scores are two orders of magnitude smaller -- around 0.016 for a
        # top-ranked hit -- so with reranking off this comparison is true for
        # every query, and every Deep search would silently take the fallback
        # path and have generic procedure language appended to it. When there
        # is no reranker score to judge, the topic anchor decides alone.
        score_is_comparable = settings.cross_encoder_reranking_enabled
        score_is_low = (
            score_is_comparable
            and initial_max_score < LOW_RERANKER_SCORE_FALLBACK_THRESHOLD
        )
        fallback_triggered = score_is_low or not top_has_topic_anchor
        anchor_bypass_triggered = not score_is_low and not top_has_topic_anchor
        if fallback_triggered:
            # When a misleading high score caused the fallback, repeat the
            # original topic once before adding generic procedure language.
            # This keeps the generalized terms from drowning the very anchor
            # that the first-pass winner lacked. Ordinary low-score fallback
            # formulation remains unchanged.
            query = " ".join(
                part
                for part in (
                    query,
                    query if anchor_bypass_triggered else "",
                    LOW_SCORE_FALLBACK_TERMS,
                )
                if part
            )
            fallback_hits, timings = await service.search_across_collections_with_timings(
                query,
                targets=targets,
                candidate_limit=40,
                result_limit=8,
                exclude_candidate_ids=set(initial_timings.scored_candidate_ids),
            )
            # Scores from two different reranker queries are not directly
            # comparable. Preserve the first pass as the topical anchor and
            # use the generalized pass to fill the wider eight-result window.
            # This adds generic procedure without displacing distinct,
            # query-specific authorities found on the first pass.
            seen = {
                (
                    str(hit.payload.get("collection_name") or ""),
                    hit.point_id,
                )
                for hit in initial_hits
            }
            procedure_sop = next(
                (
                    hit
                    for hit in fallback_hits
                    if "sop" in str(hit.payload.get("title") or "").casefold()
                    and any(
                        term in str(hit.payload.get("title") or "").casefold()
                        for term in ("fir", "complaint", "general diary")
                    )
                ),
                None,
            )
            topic_procedure_hit = (
                next(
                    (
                        hit
                        for hit in fallback_hits
                        if (
                            str(hit.payload.get("collection_name") or ""),
                            hit.point_id,
                        )
                        not in seen
                        and len(_topic_anchor_details(topic_query, hit.payload)[1])
                        >= min(2, len(focus_tokens))
                        and any(
                            term
                            in " ".join(
                                str(hit.payload.get(field) or "").casefold()
                                for field in ("title", "act_name", "text")
                            )
                            for term in PROCEDURE_ANCHOR_TERMS
                        )
                    ),
                    None,
                )
                if anchor_bypass_triggered
                else None
            )
            prioritized_fallback_hits = [
                *fallback_hits[:1],
                *([topic_procedure_hit] if topic_procedure_hit is not None else []),
                *([procedure_sop] if procedure_sop is not None else []),
                *fallback_hits[1:],
            ]
            hits = list(initial_hits)
            for hit in prioritized_fallback_hits:
                identity = (
                    str(hit.payload.get("collection_name") or ""),
                    hit.point_id,
                )
                if identity in seen:
                    continue
                hits.append(hit)
                seen.add(identity)
                if len(hits) == 8:
                    break
    except Exception as exc:
        append_stage_metric(
            state,
            stage="retrieval",
            started_ns=started_ns,
            retry_index=retry_count,
            inputs={
                "query": text_size(query),
                "target_collection_count": len(targets),
                "candidate_limit_per_collection": 40 if retry_count else 20,
                "result_limit": 8 if retry_count else 5,
            },
            outputs={"completed": False, "error_type": type(exc).__name__},
        )
        raise
    trace = list(state.get("agent_trace", []))
    trace.append(
        AgentTraceEvent(
            node="retrieval",
            details={
                "query": query,
                "retry": retry_count,
                "initial_query": initial_query,
                "topic_query": topic_query,
                "low_score_fallback_triggered": fallback_triggered,
                "low_score_fallback_threshold": LOW_RERANKER_SCORE_FALLBACK_THRESHOLD,
                "initial_max_reranker_score": initial_max_score,
                "top_topic_anchor_matched": top_has_topic_anchor,
                "top_topic_anchor_coverage": top_anchor_coverage,
                "top_topic_anchor_min_coverage": TOPIC_ANCHOR_MIN_COVERAGE,
                "top_topic_anchor_terms": sorted(top_matched_anchor_terms),
                "anchor_bypass_triggered": anchor_bypass_triggered,
                "fallback_trigger_reasons": [
                    *(
                        ["low_max_reranker_score"]
                        if initial_max_score < LOW_RERANKER_SCORE_FALLBACK_THRESHOLD
                        else []
                    ),
                    *([] if top_has_topic_anchor else ["missing_top_topic_anchor"]),
                ],
                "initial_chunk_ids": [
                    str(hit.payload.get("chunk_id")) for hit in initial_hits
                ],
                "final_max_reranker_score": max(
                    (hit.reranker_score for hit in hits),
                    default=0.0,
                ),
                "result_count": len(hits),
                "chunk_ids": [str(hit.payload.get("chunk_id")) for hit in hits],
                "collections": [target.collection_name for target in targets],
                "case_scope_applied": len(targets) > 1,
                "timings_ms": _reported_timings(timings),
            },
        )
    )
    stage_metrics = append_stage_metric(
        state,
        stage="retrieval",
        started_ns=started_ns,
        retry_index=retry_count,
        inputs={
            "query": text_size(query),
            "target_collection_count": len(targets),
            "candidate_limit_per_collection": 40 if retry_count else 20,
            "result_limit": 8 if retry_count else 5,
        },
        outputs={
            "result_count": len(hits),
            "candidate_count": timings.candidate_count,
            "raw_candidate_count": timings.raw_candidate_count,
            "deduplicated_candidate_count": timings.deduplicated_candidate_count,
            "duplicate_candidate_count": timings.duplicate_candidate_count,
            "excluded_candidate_count": timings.excluded_candidate_count,
            "low_score_fallback_triggered": fallback_triggered,
            "low_score_fallback_threshold": LOW_RERANKER_SCORE_FALLBACK_THRESHOLD,
            "initial_max_reranker_score": initial_max_score,
            "top_topic_anchor_matched": top_has_topic_anchor,
            "top_topic_anchor_coverage": top_anchor_coverage,
            "top_topic_anchor_min_coverage": TOPIC_ANCHOR_MIN_COVERAGE,
            "final_max_reranker_score": max(
                (hit.reranker_score for hit in hits),
                default=0.0,
            ),
            "reranker_input_chunk_count": timings.reranker_input_chunk_count,
            "reranker_input_characters": timings.reranker_input_characters,
            "reranker_input_utf8_bytes": timings.reranker_input_utf8_bytes,
            "reranker_query_characters_per_pair": timings.reranker_query_characters_per_pair,
            "reranker_query_utf8_bytes_per_pair": timings.reranker_query_utf8_bytes_per_pair,
            "reranker_pair_input_characters": timings.reranker_pair_input_characters,
            "reranker_pair_input_utf8_bytes": timings.reranker_pair_input_utf8_bytes,
            "reranker_max_tokens_per_query_document_pair": timings.reranker_max_length,
            "embedding_cache_hit": timings.embedding_cache_hit,
            "embedding_ms": timings.embedding_ms,
            "qdrant_ms": timings.qdrant_ms,
            "reranking_ms": timings.reranking_ms,
            "retrieval_total_ms": timings.total_ms,
        },
    )
    return {
        "retrieval_query": query,
        "retrieved_chunks": hits,
        # Identity of the evidence this pass found. Generation is deterministic
        # (temperature 0.0), so an unchanged set guarantees an unchanged answer.
        "retrieval_signature": tuple(
            sorted(str(hit.payload.get("chunk_id")) for hit in hits)
        ),
        "agent_trace": trace,
        "timings": {
            **state.get("timings", {}),
            **(
                {f"retrieval_{retry_count}_initial": _reported_timings(initial_timings)}
                if fallback_triggered
                else {}
            ),
            f"retrieval_{retry_count}": _reported_timings(timings),
        },
        "stage_metrics": stage_metrics,
    }
