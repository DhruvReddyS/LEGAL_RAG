from __future__ import annotations

from app.schemas.agents import AgentTraceEvent
from app.services.retrieval import HybridRetrievalService, RetrievalFilters
from app.services.retrieval import RetrievalTarget
from app.ingestion.init_qdrant import ADVOCATE_CASE_DATA, GLOBAL_LEGAL_CORPUS, POLICE_CASE_DATA


async def retrieval_node(state: dict, service: HybridRetrievalService) -> dict:
    retry_count = int(state.get("retry_count", 0))
    query = str(state.get("retrieval_query") or state["query"])
    if retry_count:
        entities = ", ".join(state["intent"].entities)
        query = f"{state['query']} {entities} governing law authoritative provision".strip()
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
    hits, timings = await service.search_across_collections_with_timings(
        query,
        targets=targets,
        candidate_limit=40 if retry_count else 20,
        result_limit=8 if retry_count else 5,
    )
    trace = list(state.get("agent_trace", []))
    trace.append(
        AgentTraceEvent(
            node="retrieval",
            details={
                "query": query,
                "retry": retry_count,
                "result_count": len(hits),
                "chunk_ids": [str(hit.payload.get("chunk_id")) for hit in hits],
                "collections": [target.collection_name for target in targets],
                "case_scope_applied": len(targets) > 1,
                "timings_ms": timings.__dict__,
            },
        )
    )
    return {
        "retrieval_query": query,
        "retrieved_chunks": hits,
        "agent_trace": trace,
        "timings": {**state.get("timings", {}), f"retrieval_{retry_count}": timings.__dict__},
    }
