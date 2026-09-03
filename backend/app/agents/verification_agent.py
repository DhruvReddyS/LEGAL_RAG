from __future__ import annotations

import re
from time import perf_counter_ns
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.agents import AgentTraceEvent, ClaimVerification, VerificationResult
from app.services.generation import INSUFFICIENT_EVIDENCE
from app.services.llm import OllamaClient
from app.services.pipeline_telemetry import append_stage_metric, structured_with_metrics, text_size


# Reasoning caps evidence per chunk; verification did not, so the premise
# block grew to ~12,900 tokens - 79% of the context window and 40-50 seconds
# of prefill before the first output token. Legal chunks average ~700 words,
# so 2,500 characters keeps the provision that grounds a claim while removing
# the surrounding material no claim cites.
MAX_PREMISE_CHARACTERS = 2500

MARKER_RE = re.compile(r"\[SRC:([^\]]+)\]")
CATEGORY_RE = re.compile(
    r"^\[(DIRECT_ANSWER|LEGAL_BASIS|APPLICATION|NEXT_STEP|LIMIT)\]\s*",
    re.IGNORECASE,
)
CATEGORY_MAP = {
    "direct_answer": "direct_answer",
    "legal_basis": "legal_basis",
    "application": "application",
    "next_step": "next_step",
    "limit": "limit",
}


class VerdictItem(BaseModel):
    index: int = Field(ge=1)
    verdict: Literal["yes", "partial", "no"]
    reason: str = ""


class VerificationBatch(BaseModel):
    claims: list[VerdictItem] = Field(default_factory=list)


def _claim_marker_pairs(answer: str) -> list[tuple[str, str]]:
    return [(claim, chunk_id) for _, claim, chunk_id in _categorized_claim_marker_pairs(answer)]


def _categorized_claim_marker_pairs(answer: str) -> list[tuple[str, str, str]]:
    pairs: list[tuple[str, str, str]] = []
    previous_end = 0
    previous_claim = ""
    previous_category = "legal_basis"
    for marker in MARKER_RE.finditer(answer):
        # Text between consecutive markers is the claim for the current marker.
        # This avoids sentence splitting errors on legal abbreviations such as
        # "U.P.", "Cr.P.C.", and citation punctuation.
        claim = answer[previous_end : marker.start()].strip(" \n\t.;")
        if not claim:
            claim = previous_claim
            category = previous_category
        else:
            category_match = CATEGORY_RE.match(claim)
            category = (
                CATEGORY_MAP[category_match.group(1).casefold()]
                if category_match
                else "legal_basis"
            )
            if category_match:
                claim = claim[category_match.end() :].strip()
        if claim:
            pairs.append((category, claim, marker.group(1).strip()))
            previous_claim = claim
            previous_category = category
        previous_end = marker.end()
    return pairs


def _format_verification_items(
    valid_pairs: list[tuple[str, str, str]],
    hits_by_id: dict[str, str],
) -> str:
    premise_ids = list(dict.fromkeys(chunk_id for _, _, chunk_id in valid_pairs))
    source_labels = {
        chunk_id: f"SOURCE_{index}"
        for index, chunk_id in enumerate(premise_ids, 1)
    }
    indexed_pairs = list(enumerate(valid_pairs, 1))
    source_blocks: list[str] = []
    for chunk_id in premise_ids:
        source_claims = "\n\n".join(
            f"CLAIM {index}: {claim}\nSOURCE_REF: {source_labels[chunk_id]}"
            for index, (_, claim, pair_chunk_id) in indexed_pairs
            if pair_chunk_id == chunk_id
        )
        source_blocks.append(
            f"{source_labels[chunk_id]}\nCHUNK_ID: {chunk_id}\n"
            f"CLAIMS AGAINST {source_labels[chunk_id]}:\n{source_claims}\n\n"
            f"PREMISE_TEXT FOR {source_labels[chunk_id]}:\n{hits_by_id[chunk_id]}"
        )
    return "\n\n===== NEXT SOURCE =====\n\n".join(source_blocks)


async def verification_node(state: dict, llm: OllamaClient) -> dict:
    started_ns = perf_counter_ns()
    retry_index = int(state.get("retry_count", 0))
    draft = str(state.get("draft_answer") or "")
    hits_by_id = {
        str(hit.payload.get("chunk_id")): str(hit.payload.get("text") or "")[
            :MAX_PREMISE_CHARACTERS
        ]
        for hit in state.get("retrieved_chunks", [])
    }
    pairs = _categorized_claim_marker_pairs(draft)
    valid_pairs = [
        (category, claim, chunk_id)
        for category, claim, chunk_id in pairs
        if chunk_id in hits_by_id
    ]
    missing = [claim for _, claim, chunk_id in pairs if chunk_id not in hits_by_id]

    verified: list[ClaimVerification] = []
    items = ""
    prompt = ""
    llm_calls: list[dict] = []
    fallback_used = False
    if valid_pairs:
        items = _format_verification_items(valid_pairs, hits_by_id)
        prompt = f"""Each source block contains every CLAIM for one source followed by its PREMISE_TEXT.
Verify every numbered CLAIM only against the PREMISE_TEXT in its own
source block. Do not use another block. Return one result for every claim using its exact numeric
claim index. Verdict must be yes, partial, or no. Use yes only when the premise directly entails the
material claim; partial for incomplete support; no otherwise. Return JSON.

{items}"""
        try:
            batch, llm_calls = await structured_with_metrics(llm, prompt, VerificationBatch)
            seen_indexes: set[int] = set()
            for item in batch.claims:
                if item.index > len(valid_pairs) or item.index in seen_indexes:
                    continue
                seen_indexes.add(item.index)
                category, claim, chunk_id = valid_pairs[item.index - 1]
                verdict = item.verdict.casefold()
                if verdict not in {"yes", "partial", "no"}:
                    verdict = "no"
                verified.append(
                    ClaimVerification(
                        claim=claim,
                        chunk_id=chunk_id,
                        category=category,
                        verdict=verdict,
                        reason=item.reason,
                    )
                )
        except RuntimeError as exc:
            llm_calls = list(getattr(exc, "telemetry_metrics", []))
            fallback_used = True
            verified = [
                ClaimVerification(
                    claim=claim,
                    chunk_id=chunk_id,
                    category=category,
                    verdict="partial",
                    reason="Verifier unavailable",
                )
                for category, claim, chunk_id in valid_pairs
            ]

    accounted = {(item.claim, item.chunk_id) for item in verified}
    for category, claim, chunk_id in valid_pairs:
        if (claim, chunk_id) not in accounted:
            verified.append(
                ClaimVerification(
                    claim=claim,
                    chunk_id=chunk_id,
                    category=category,
                    verdict="no",
                    reason="No verifier result",
                )
            )
    total = max(len(pairs), 1)
    support = sum(1.0 if item.verdict == "yes" else 0.5 if item.verdict == "partial" else 0.0 for item in verified)
    score = 0.0 if not pairs or draft == INSUFFICIENT_EVIDENCE else support / total
    unsupported = missing + [item.claim for item in verified if item.verdict == "no"]
    result = VerificationResult(
        score=max(0.0, min(1.0, score)),
        supported_claims=sum(item.verdict == "yes" for item in verified),
        total_claims=len(pairs),
        claims=verified,
        unsupported_claims=list(dict.fromkeys(unsupported)),
    )
    trace = list(state.get("agent_trace", []))
    trace.append(
        AgentTraceEvent(
            node="verification",
            details={
                "score": result.score,
                "claims": result.total_claims,
                "unsupported": len(result.unsupported_claims),
            },
        )
    )
    stage_metrics = append_stage_metric(
        state,
        stage="verification",
        started_ns=started_ns,
        retry_index=retry_index,
        inputs={
            "draft": text_size(draft),
            "retrieved_chunk_count": len(hits_by_id),
            "claim_marker_count": len(pairs),
            "valid_claim_count": len(valid_pairs),
            "verification_items": text_size(items),
            "prompt": text_size(prompt),
            "max_premise_characters": MAX_PREMISE_CHARACTERS,
        },
        outputs={
            "verified_claim_count": len(verified),
            "unsupported_claim_count": len(result.unsupported_claims),
            "score": result.score,
            "fallback_used": fallback_used,
            "llm_skipped": not valid_pairs,
        },
        llm_calls=llm_calls,
    )
    return {
        "verification_result": result,
        "agent_trace": trace,
        "stage_metrics": stage_metrics,
    }
