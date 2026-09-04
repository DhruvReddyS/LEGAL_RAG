from __future__ import annotations

import re
from time import perf_counter_ns

from app.schemas.agents import AgentCitation, AgentTraceEvent
from app.services.citation_status import citation_currency
from app.services.generation import INSUFFICIENT_EVIDENCE
from app.services.pipeline_telemetry import append_stage_metric, text_size


MARKER_RE = re.compile(r"\[SRC:([^\]]+)\]")
PROFESSIONAL_SECTION_LABELS = {
    "direct_answer": "Direct answer",
    "legal_basis": "Verified legal basis",
    "application": "Application to your situation",
    "next_step": "Practical next steps",
    "limit": "Important limits and uncertainties",
}

CITIZEN_SECTION_LABELS = {
    "direct_answer": "Direct answer",
    "legal_basis": "Why this is the legal position",
    "application": "How this applies to you",
    "next_step": "What you can do now",
    "limit": "Important limits",
}


def response_generation_node(state: dict) -> dict:
    started_ns = perf_counter_ns()
    result = state["verification_result"]
    hits = list(state.get("retrieved_chunks", []))
    hit_by_id = {str(hit.payload.get("chunk_id")): hit for hit in hits}
    if result.score < 0.5:
        answer = INSUFFICIENT_EVIDENCE
        cited_ids: list[str] = []
    else:
        # Rebuild the response from individually verified claim-marker pairs.
        # Removing whole lines is unsafe because one paragraph can contain both
        # supported and unsupported claims.
        role = str(state.get("role") or "citizen")
        section_labels = (
            CITIZEN_SECTION_LABELS
            if role == "citizen"
            else PROFESSIONAL_SECTION_LABELS
        )
        supported_by_category: dict[str, list[str]] = {
            category: [] for category in section_labels
        }
        supported_sources: dict[tuple[str, str], list[str]] = {}
        for claim in result.claims:
            key = (claim.category, claim.claim)
            # A partial verdict does not identify which words are supported.
            # Publishing the entire compound claim would leak the unsupported
            # portion, so only directly entailed claims can reach the user.
            if claim.verdict != "yes":
                continue
            hit = hit_by_id.get(claim.chunk_id)
            # A source explicitly marked superseded cannot ground a user-facing
            # legal proposition even when its historical text entails the claim.
            if hit is None or hit.payload.get("is_superseded") is True:
                continue
            supported_sources.setdefault(key, [])
            if claim.chunk_id not in supported_sources[key]:
                supported_sources[key].append(claim.chunk_id)
        for (category, claim), chunk_ids in supported_sources.items():
            markers = " ".join(f"[SRC:{chunk_id}]" for chunk_id in chunk_ids)
            supported_by_category[category].append(
                f"{claim.rstrip(' .')} {markers}."
            )
        sections: list[str] = []
        for category, label in section_labels.items():
            claims = supported_by_category[category]
            if not claims:
                continue
            if category == "direct_answer":
                body = "\n\n".join(claims)
            elif role == "citizen" and category == "next_step":
                body = "\n".join(
                    f"{number}. {claim}" for number, claim in enumerate(claims, 1)
                )
            else:
                body = "\n".join(f"- {claim}" for claim in claims)
            sections.append(f"## {label}\n\n{body}")
        answer = "\n\n".join(sections) or INSUFFICIENT_EVIDENCE
        cited_ids = list(dict.fromkeys(MARKER_RE.findall(answer)))

    published_score = (
        result.supported_claims / max(result.total_claims, 1)
        if answer != INSUFFICIENT_EVIDENCE
        else 0.0
    )

    verdict_priority = {"no": 0, "partial": 1, "yes": 2}
    verdict_by_id: dict[str, str] = {}
    for item in result.claims:
        current = verdict_by_id.get(item.chunk_id, "no")
        if verdict_priority[item.verdict] > verdict_priority[current]:
            verdict_by_id[item.chunk_id] = item.verdict
    citations: list[AgentCitation] = []
    number_by_id: dict[str, int] = {}
    for chunk_id in cited_ids:
        hit = hit_by_id.get(chunk_id)
        if hit is None:
            continue
        payload = hit.payload
        currency, replaced_by, repealed_on = citation_currency(payload)
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
                current_status=currency,
                replaced_by=replaced_by,
                repealed_on=repealed_on,
            )
        )
    answer = MARKER_RE.sub(lambda match: f"[Source {number_by_id[match.group(1)]}]" if match.group(1) in number_by_id else "", answer)
    if answer != INSUFFICIENT_EVIDENCE:
        currency_unverified = any(
            hit_by_id[chunk_id].payload.get("corpus_scope") != "private_case"
            and hit_by_id[chunk_id].payload.get("is_current") is not True
            for chunk_id in cited_ids
            if chunk_id in hit_by_id
        )
        if currency_unverified:
            answer += (
                "\n\n## Source currency\n\n"
                "The cited corpus material supports the statements above, but its current-law "
                "status is not verified in the corpus metadata. Check the latest official text "
                "and amendments before relying on it for a live matter."
            )
        answer += (
            "\n\n---\n\n*Legal decision-support information, not a substitute for "
            "advice from a qualified professional who has reviewed the complete facts and current law.*"
        )
    strength = "strong" if published_score > 0.85 else "moderate" if published_score >= 0.5 else "insufficient"
    trace = list(state.get("agent_trace", []))
    trace.append(AgentTraceEvent(node="response_generation", details={"citations": len(citations), "evidence_strength": strength}))
    stage_metrics = append_stage_metric(
        state,
        stage="response_generation",
        started_ns=started_ns,
        retry_index=int(state.get("retry_count", 0)),
        inputs={
            "draft": text_size(str(state.get("draft_answer") or "")),
            "retrieved_chunk_count": len(hits),
            "verified_claim_count": len(result.claims),
        },
        outputs={
            "answer": text_size(answer),
            "citation_count": len(citations),
            "confidence_score": published_score,
            "evidence_strength": strength,
        },
    )
    return {
        "final_answer": answer,
        "citations": citations,
        "confidence_score": published_score,
        "evidence_strength": strength,
        "agent_trace": trace,
        "stage_metrics": stage_metrics,
    }
