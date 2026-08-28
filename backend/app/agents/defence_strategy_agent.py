from __future__ import annotations

import re

from app.agents.verification_agent import VerificationBatch
from app.ingestion.init_qdrant import ADVOCATE_CASE_DATA, GLOBAL_LEGAL_CORPUS
from app.schemas.agents import AgentCitation
from app.schemas.strategy import (
    DefenceAnalysisDraft,
    DefenceAnalysisResponse,
    VerifiedStrategyPoint,
)
from app.services.llm import OllamaClient
from app.services.retrieval import (
    HybridRetrievalService,
    RetrievalFilters,
    RetrievalHit,
    RetrievalTarget,
)


STRATEGY_DISCLAIMER = (
    "Professional review required. This analysis identifies lawful factual, evidentiary and "
    "procedural issues; it is not a prediction, legal advice, or a recommendation to conceal, "
    "alter or fabricate evidence or influence a witness. Confirm that every cited provision and "
    "authority remains current before relying on it."
)

_UNSAFE_TACTIC = re.compile(
    r"\b(?:destroy|delete|erase|hide|conceal|fabricate|forge|plant|tamper(?:\s+with)?|"
    r"bribe|threaten|intimidate)\b.{0,40}\b(?:evidence|records?|logs?|documents?|witness(?:es)?|statements?)\b",
    flags=re.IGNORECASE,
)


def _evidence_text(hits: list[RetrievalHit]) -> str:
    return "\n\n---\n\n".join(
        f"CHUNK_ID: {hit.payload.get('chunk_id')}\n"
        f"TITLE: {hit.payload.get('title', 'Case evidence')}\n"
        f"TEXT: {str(hit.payload.get('text', ''))[:2400]}"
        for hit in hits
    )


def _citations(hits: list[RetrievalHit], used_ids: set[str]) -> list[AgentCitation]:
    citations: list[AgentCitation] = []
    for hit in hits:
        payload = hit.payload
        chunk_id = str(payload.get("chunk_id") or "")
        if chunk_id not in used_ids:
            continue
        citations.append(
            AgentCitation(
                number=len(citations) + 1,
                chunk_id=chunk_id,
                title=str(payload.get("title") or "Case evidence"),
                source_type=str(payload.get("source_type") or payload.get("doc_type") or "case_document"),
                page_start=int(payload.get("page_start") or 1),
                page_end=int(payload.get("page_end") or payload.get("page_start") or 1),
                court=payload.get("court") or None,
                act_name=payload.get("act_name") or None,
                section=payload.get("section") or None,
                source_url=payload.get("source_url") or None,
                excerpt=str(payload.get("text") or "")[:1200],
                retrieval_score=hit.reranker_score,
                verification_status="verified",
                current_status=(
                    "not_applicable"
                    if payload.get("corpus_scope") == "private_case"
                    else "current"
                    if payload.get("is_current") is True
                    else "superseded"
                    if payload.get("is_superseded") is True
                    else "status_unverified"
                ),
            )
        )
    return citations


class DefenceStrategyAgent:
    def __init__(self, retrieval: HybridRetrievalService, llm: OllamaClient) -> None:
        self.retrieval = retrieval
        self.llm = llm

    async def run(
        self,
        *,
        case_id: str,
        case_scenario: str,
        advocate_position: str | None,
    ) -> DefenceAnalysisResponse:
        query = (
            "Indian criminal defence conscious possession mens rea prosecution burden vehicle "
            "contraband statutory presumptions NDPS section 35 section 54 if applicable "
            "admissibility procedural safeguards contradictions exculpatory evidence "
            f"{case_scenario} {advocate_position or ''}"
        )[:4000]
        hits, _ = await self.retrieval.search_across_collections_with_timings(
            query,
            targets=[
                RetrievalTarget(
                    GLOBAL_LEGAL_CORPUS,
                    RetrievalFilters(current_only=False, corpus_tiers=["gold", "extended"]),
                ),
                RetrievalTarget(
                    ADVOCATE_CASE_DATA,
                    RetrievalFilters(corpus_tiers=[], case_ids=[case_id]),
                ),
            ],
            candidate_limit=30,
            result_limit=10,
        )
        if not hits:
            return DefenceAnalysisResponse(
                summary="Insufficient verified evidence for a defence analysis.",
                points=[],
                citations=[],
                confidence_score=0,
                evidence_strength="insufficient",
                rejected_point_count=0,
                disclaimer=STRATEGY_DISCLAIMER,
            )

        scenario_source_id = "case-scenario-input"
        scenario_hit = RetrievalHit(
            point_id=scenario_source_id,
            payload={
                "chunk_id": scenario_source_id,
                "title": "User-supplied case scenario (unverified)",
                "source_type": "user_supplied_scenario",
                "page_start": 1,
                "page_end": 1,
                "text": case_scenario,
            },
            dense_score=None,
            sparse_score=None,
            fused_score=0,
            reranker_score=0,
        )
        hits.append(scenario_hit)
        prompt = f"""Act as an Indian advocate's research assistant. Identify the strongest lawful
defence issues and the strongest likely prosecution responses. Do not predict the outcome. Do not
recommend hiding, deleting, altering or fabricating evidence, influencing witnesses, evasion, or
delay tactics. Every point must cite one or more exact CHUNK_ID values from EVIDENCE. Treat the user
scenario as an allegation, not established fact. Every point must cite case-scenario-input. A legal,
evidentiary or procedural proposition must additionally cite at least one retrieved corpus CHUNK_ID.
Return JSON matching the schema. Return at most five points, prioritizing material issues supported
by the strongest evidence.

CASE SCENARIO:
{case_scenario}

ADVOCATE POSITION:
{advocate_position or '(none supplied)'}

EVIDENCE:
{_evidence_text(hits)}"""
        draft = await self.llm.structured(prompt, DefenceAnalysisDraft)
        hits_by_id = {
            str(hit.payload.get("chunk_id")): str(hit.payload.get("text") or "")
            for hit in hits
            if hit.payload.get("chunk_id")
        }
        candidates = []
        for point in draft.points:
            ids = set(point.source_chunk_ids)
            requires_law = point.category != "further_fact_needed"
            if (
                not all(chunk_id in hits_by_id for chunk_id in ids)
                or (requires_law and not (ids - {scenario_source_id}))
                or _UNSAFE_TACTIC.search(point.point)
            ):
                continue
            # The scenario is always an unverified premise for strategy work;
            # attach it deterministically instead of relying on the LLM to copy
            # the synthetic identifier into every otherwise valid point.
            ids.add(scenario_source_id)
            candidates.append(
                point.model_copy(update={"source_chunk_ids": sorted(ids)})
            )
        rejected = len(draft.points) - len(candidates)
        if candidates:
            verification_items = "\n\n".join(
                f"CLAIM {index}: {point.point}\nPREMISES:\n"
                + "\n".join(hits_by_id[item] for item in point.source_chunk_ids)
                for index, point in enumerate(candidates, 1)
            )
            verification = await self.llm.structured(
                "Verify each CLAIM only against its PREMISES. Use yes, partial, or no and the "
                f"numeric index. Return JSON.\n\n{verification_items}",
                VerificationBatch,
            )
        else:
            verification = VerificationBatch()

        verdict_by_index = {
            item.index: item
            for item in verification.claims
            if 1 <= item.index <= len(candidates)
        }
        accepted: list[VerifiedStrategyPoint] = []
        support = 0.0
        for index, point in enumerate(candidates, 1):
            verdict = verdict_by_index.get(index)
            if verdict is None or verdict.verdict != "yes":
                rejected += 1
                continue
            support += 1.0
            accepted.append(
                VerifiedStrategyPoint(
                    **point.model_dump(),
                    verification="yes",
                    verification_reason=verdict.reason,
                )
            )
        total = max(len(draft.points), 1)
        confidence = support / total
        strength = "strong" if confidence > 0.85 else "moderate" if confidence >= 0.5 else "insufficient"
        used_ids = {item for point in accepted for item in point.source_chunk_ids}
        summary = (
            f"{len(accepted)} of {len(draft.points)} proposed points were directly supported by "
            "the supplied scenario and retrieved evidence."
        )
        if strength == "insufficient":
            summary = "Insufficient overall grounding. " + summary
        return DefenceAnalysisResponse(
            summary=summary,
            points=accepted,
            citations=_citations(hits, used_ids),
            confidence_score=round(confidence, 4),
            evidence_strength=strength,
            rejected_point_count=rejected,
            disclaimer=STRATEGY_DISCLAIMER,
        )
