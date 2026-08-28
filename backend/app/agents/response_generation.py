from __future__ import annotations

import re

from app.schemas.agents import AgentCitation, AgentTraceEvent
from app.services.generation import INSUFFICIENT_EVIDENCE


MARKER_RE = re.compile(r"\[SRC:([^\]]+)\]")


def response_generation_node(state: dict) -> dict:
    result = state["verification_result"]
    hits = list(state.get("retrieved_chunks", []))
    if result.score < 0.5:
        answer = INSUFFICIENT_EVIDENCE
        cited_ids: list[str] = []
    else:
        # Rebuild the response from individually verified claim-marker pairs.
        # Removing whole lines is unsafe because one paragraph can contain both
        # supported and unsupported claims.
        supported_parts: list[str] = []
        seen: set[tuple[str, str]] = set()
        for claim in result.claims:
            key = (claim.claim, claim.chunk_id)
            # A partial verdict does not identify which words are supported.
            # Publishing the entire compound claim would leak the unsupported
            # portion, so only directly entailed claims can reach the user.
            if claim.verdict != "yes" or key in seen:
                continue
            seen.add(key)
            supported_parts.append(
                f"{claim.claim.rstrip(' .')} [SRC:{claim.chunk_id}]."
            )
        answer = "\n\n".join(supported_parts) or INSUFFICIENT_EVIDENCE
        cited_ids = list(dict.fromkeys(MARKER_RE.findall(answer)))

    published_score = (
        result.supported_claims / max(result.total_claims, 1)
        if answer != INSUFFICIENT_EVIDENCE
        else 0.0
    )

    hit_by_id = {str(hit.payload.get("chunk_id")): hit for hit in hits}
    verdict_by_id = {item.chunk_id: item.verdict for item in result.claims}
    citations: list[AgentCitation] = []
    number_by_id: dict[str, int] = {}
    for chunk_id in cited_ids:
        hit = hit_by_id.get(chunk_id)
        if hit is None:
            continue
        payload = hit.payload
        number = len(citations) + 1
        number_by_id[chunk_id] = number
        citations.append(
            AgentCitation(
                number=number,
                chunk_id=chunk_id,
                title=str(payload.get("title") or "Unknown source"),
                source_type=str(payload.get("source_type") or "unknown"),
                page_start=int(payload.get("page_start") or 1),
                page_end=int(payload.get("page_end") or payload.get("page_start") or 1),
                court=payload.get("court") or None,
                act_name=payload.get("act_name") or None,
                section=payload.get("section") or None,
                source_url=payload.get("source_url") or None,
                excerpt=str(payload.get("text") or "")[:1200],
                retrieval_score=hit.reranker_score,
                verification_status=(
                    "verified"
                    if verdict_by_id.get(chunk_id) == "yes"
                    else "partial"
                    if verdict_by_id.get(chunk_id) == "partial"
                    else "unverified"
                ),
                current_status=(
                    "current"
                    if payload.get("is_current") is True
                    else "superseded"
                    if payload.get("is_superseded") is True
                    else "not_applicable"
                    if payload.get("corpus_scope") == "private_case"
                    else "status_unverified"
                ),
            )
        )
    answer = MARKER_RE.sub(lambda match: f"[Source {number_by_id[match.group(1)]}]" if match.group(1) in number_by_id else "", answer)
    strength = "strong" if published_score > 0.85 else "moderate" if published_score >= 0.5 else "insufficient"
    trace = list(state.get("agent_trace", []))
    trace.append(AgentTraceEvent(node="response_generation", details={"citations": len(citations), "evidence_strength": strength}))
    return {
        "final_answer": answer,
        "citations": citations,
        "confidence_score": published_score,
        "evidence_strength": strength,
        "agent_trace": trace,
    }
