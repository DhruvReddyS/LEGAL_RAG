from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.agents import AgentTraceEvent, ClaimVerification, VerificationResult
from app.services.generation import INSUFFICIENT_EVIDENCE
from app.services.llm import OllamaClient


MARKER_RE = re.compile(r"\[SRC:([^\]]+)\]")


class VerdictItem(BaseModel):
    index: int = Field(ge=1)
    verdict: Literal["yes", "partial", "no"]
    reason: str = ""


class VerificationBatch(BaseModel):
    claims: list[VerdictItem] = Field(default_factory=list)


def _claim_marker_pairs(answer: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    previous_end = 0
    previous_claim = ""
    for marker in MARKER_RE.finditer(answer):
        # Text between consecutive markers is the claim for the current marker.
        # This avoids sentence splitting errors on legal abbreviations such as
        # "U.P.", "Cr.P.C.", and citation punctuation.
        claim = answer[previous_end : marker.start()].strip(" \n\t.;")
        if not claim:
            claim = previous_claim
        if claim:
            pairs.append((claim, marker.group(1).strip()))
            previous_claim = claim
        previous_end = marker.end()
    return pairs


async def verification_node(state: dict, llm: OllamaClient) -> dict:
    draft = str(state.get("draft_answer") or "")
    hits_by_id = {
        str(hit.payload.get("chunk_id")): str(hit.payload.get("text") or "")
        for hit in state.get("retrieved_chunks", [])
    }
    pairs = _claim_marker_pairs(draft)
    valid_pairs = [(claim, chunk_id) for claim, chunk_id in pairs if chunk_id in hits_by_id]
    missing = [claim for claim, chunk_id in pairs if chunk_id not in hits_by_id]

    verified: list[ClaimVerification] = []
    if valid_pairs:
        items = "\n\n".join(
            f"CLAIM {index}: {claim}\nCHUNK_ID: {chunk_id}\nPREMISE: {hits_by_id[chunk_id]}"
            for index, (claim, chunk_id) in enumerate(valid_pairs, 1)
        )
        prompt = f"""Verify each numbered CLAIM only against its PREMISE. Return one result per claim
using the exact numeric index. Verdict must be yes, partial, or no. Use yes only when the premise
directly entails the material claim; partial for incomplete support; no otherwise. Return JSON.

{items}"""
        try:
            batch = await llm.structured(prompt, VerificationBatch)
            seen_indexes: set[int] = set()
            for item in batch.claims:
                if item.index > len(valid_pairs) or item.index in seen_indexes:
                    continue
                seen_indexes.add(item.index)
                claim, chunk_id = valid_pairs[item.index - 1]
                verdict = item.verdict.casefold()
                if verdict not in {"yes", "partial", "no"}:
                    verdict = "no"
                verified.append(
                    ClaimVerification(
                        claim=claim,
                        chunk_id=chunk_id,
                        verdict=verdict,
                        reason=item.reason,
                    )
                )
        except RuntimeError:
            verified = [
                ClaimVerification(claim=claim, chunk_id=chunk_id, verdict="partial", reason="Verifier unavailable")
                for claim, chunk_id in valid_pairs
            ]

    accounted = {(item.claim, item.chunk_id) for item in verified}
    for claim, chunk_id in valid_pairs:
        if (claim, chunk_id) not in accounted:
            verified.append(
                ClaimVerification(claim=claim, chunk_id=chunk_id, verdict="no", reason="No verifier result")
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
    return {"verification_result": result, "agent_trace": trace}
