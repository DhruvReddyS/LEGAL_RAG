from __future__ import annotations

import re
from functools import lru_cache
from time import perf_counter_ns
from typing import Literal

from pydantic import BaseModel, Field, create_model

from app.core.config import settings
from app.schemas.agents import AgentTraceEvent, ClaimVerification, VerificationResult
from app.services.generation import INSUFFICIENT_EVIDENCE
from app.services.llm import OllamaClient
from app.services.pipeline_telemetry import append_stage_metric, structured_with_metrics, text_size


# Reasoning caps evidence per chunk; verification did not, so the premise
# block grew to ~12,900 tokens - 79% of the context window and 40-50 seconds
# of prefill before the first output token. Legal chunks average ~700 words,
# so 1,800 characters keeps the provision that grounds a claim while removing
# the surrounding material no claim cites.
MAX_PREMISE_CHARACTERS = 1800

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
    reason: str = Field(default="", max_length=120)


# The grammar cannot force more verdicts than the base schema allows, and a
# claim may cite three sources, so ten claims can produce thirty pairs.
MAX_VERDICTS = 32


class VerificationBatch(BaseModel):
    # Positional verdicts are the production format. Ten short strings replace
    # ten repeated objects with indexes and reasons, cutting verifier decode
    # substantially. `claims` remains accepted for compatibility with stored
    # fixtures and as a defensive fallback if a model follows the older shape.
    verdicts: list[Literal["yes", "partial", "no"]] = Field(
        default_factory=list,
        max_length=MAX_VERDICTS,
    )
    claims: list[VerdictItem] = Field(default_factory=list)


@lru_cache(maxsize=MAX_VERDICTS + 1)
def verdicts_for_exactly(claim_count: int) -> type[VerificationBatch]:
    """A verdict schema the host cannot satisfy with a short array.

    The verifier routinely returned fewer verdicts than it was sent --
    measured runs came back with three verdicts for ten claims and for
    fourteen -- and every consequence of that was bad in both directions at
    once. The missing claims were asked for a second time, which is another
    prompt, another prefill of the same premises and another decode; and any
    claim still without a verdict after that was recorded as refuted, which
    suppressed verified law the verifier had never actually rejected.

    `minItems == maxItems == claim_count`, with `verdicts` required, is
    compiled into the sampling grammar, so the array cannot close early and
    cannot run long. The model is not being asked more politely to return
    every verdict; it is made unable to do otherwise.

    The bound is applied to the *requested* schema only. Validation stays as
    permissive as the base class, deliberately: when a host cannot build the
    grammar the client retries with plain JSON mode, and a model answering in
    the older `claims` shape must still parse. Rejecting it would turn a
    formatting difference into "Verifier unavailable", which marks every
    claim partial -- strictly worse than the short array this exists to fix.

    Deriving the schema per claim count rather than fixing it keeps the
    positional contract: verdict *i* belongs to claim *i*, so a short array
    would silently shift every later verdict onto the wrong claim.
    """
    bounded = max(1, min(claim_count, MAX_VERDICTS))

    class BoundedVerificationBatch(VerificationBatch):
        @classmethod
        def model_json_schema(cls, *args, **kwargs):  # type: ignore[override]
            schema = dict(VerificationBatch.model_json_schema(*args, **kwargs))
            verdicts = dict(schema["properties"]["verdicts"])
            verdicts["minItems"] = bounded
            verdicts["maxItems"] = bounded
            schema["properties"] = {**schema["properties"], "verdicts": verdicts}
            # Required in the request, so the grammar cannot omit the array
            # and fall back to the object form. `claims` stays optional.
            schema["required"] = ["verdicts"]
            schema["title"] = f"VerificationBatchOf{bounded}"
            return schema

    BoundedVerificationBatch.__name__ = f"VerificationBatchOf{bounded}"
    BoundedVerificationBatch.__qualname__ = BoundedVerificationBatch.__name__
    return BoundedVerificationBatch


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
    *,
    start_index: int = 0,
    explicit_indexes: list[int] | None = None,
) -> str:
    """Render claims grouped under the source each one cites.

    `explicit_indexes` keeps a claim's original number when only a subset is
    re-sent, so a second request can be scoped to what was skipped without the
    numbering drifting away from the first.
    """
    premise_ids = list(dict.fromkeys(chunk_id for _, _, chunk_id in valid_pairs))
    source_labels = {
        chunk_id: f"SOURCE_{index}"
        for index, chunk_id in enumerate(premise_ids, 1)
    }
    indexed_pairs = (
        list(zip(explicit_indexes, valid_pairs, strict=True))
        if explicit_indexes is not None
        else list(enumerate(valid_pairs, start_index + 1))
    )
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


def build_premises(chunks) -> tuple[dict[str, str], int]:
    """Premise text per chunk, capped, with the number of chunks that lost text.

    The verifier sees at most MAX_PREMISE_CHARACTERS of a chunk. A claim
    supported only by text past the cap is judged unsupported, which costs a
    retry and can end in an abstention -- and the provisions most likely to
    exceed the cap are long enumerations, exactly the ones worth citing. The
    cap is a deliberate cost control and stays. Its invisibility was not: a
    truncation that is never counted cannot be tuned against evidence.
    """
    premises: dict[str, str] = {}
    truncated = 0
    for chunk in chunks:
        chunk_id = str(chunk.payload.get("chunk_id"))
        text = str(chunk.payload.get("text") or "")
        if len(text) > MAX_PREMISE_CHARACTERS:
            truncated += 1
        premises[chunk_id] = text[:MAX_PREMISE_CHARACTERS]
    return premises, truncated


async def verification_node(state: dict, llm: OllamaClient) -> dict:
    started_ns = perf_counter_ns()
    retry_index = int(state.get("retry_count", 0))
    draft = str(state.get("draft_answer") or "")
    hits_by_id, truncated_premise_count = build_premises(
        state.get("retrieved_chunks", [])
    )
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
    # Whether the "you skipped some claims" request had to be made. With the
    # exact-length grammar in place this should stay false; recording it is
    # how a host that ignores the bound becomes visible instead of merely
    # slower.
    second_request_used = False
    if valid_pairs:
        items = _format_verification_items(valid_pairs, hits_by_id)
        # Stating the expected verdict count is measured, effective, and not
        # free, so it travels with the same setting as the grammar.
        #
        # Measured over three 21-run passes on one query set. With the count
        # stated, the "you skipped some claims" second request fell from 9
        # runs in 21 to none and unadjudicated claims from 0.095 per query to
        # zero -- and the grammar turned out to be unnecessary to achieve
        # that, because a run with the sentence and no grammar produced the
        # identical 0 of 21 and the identical 2.143 model calls per query.
        #
        # The same two runs also published 2.43 citations per query against
        # the baseline's 3.14, and graded 28.6% of answers insufficient
        # against 9.5%. The mechanism is credible: a claim the verifier used
        # to leave unjudged was excluded from the support denominator, while
        # a forced verdict on that claim can be an explicit "no" that counts
        # against the score -- enough to make a first pass publishable, which
        # stops the retry firing, and the retry was where two of q04's six
        # citations came from. Retries went from 3 runs in 21 to none in both
        # runs that carried this sentence.
        #
        # Not proven, because those runs also decoded 58% faster than the
        # baseline and this pipeline is not reproducible: the same question
        # published 312 words at verification 0.75 on one repeat and
        # abstained at 0.43 on the next. Fewer citations is the one direction
        # a citizen surface cannot afford to move in by accident, so the
        # default is the behaviour that produced more of them.
        count_instruction = (
            f"There are {len(valid_pairs)} claims in total; return exactly "
            f"{len(valid_pairs)} verdicts in numeric order"
            if settings.verification_exact_verdict_grammar_enabled
            else "Return one verdict per claim in numeric order"
        )
        prompt = f"""Each source block contains numbered claims and its premise.
Judge every claim only against the premise in its own block. {count_instruction} as JSON:
{{"verdicts":["yes","partial","no"]}}. Use yes only when the premise directly
entails the material claim, partial for incomplete support, and no otherwise. Return no explanations.

{items}"""
        try:
            verification_budget = min(256, max(128, 96 + len(valid_pairs) * 12))
            batch, llm_calls = await structured_with_metrics(
                llm,
                prompt,
                (
                    verdicts_for_exactly(len(valid_pairs))
                    if settings.verification_exact_verdict_grammar_enabled
                    else VerificationBatch
                ),
                num_predict=verification_budget,
            )
            seen_indexes: set[int] = set()

            def collect(result: VerificationBatch) -> None:
                if result.verdicts:
                    for index, verdict in enumerate(result.verdicts, start=1):
                        if index > len(valid_pairs) or index in seen_indexes:
                            continue
                        seen_indexes.add(index)
                        category, claim, chunk_id = valid_pairs[index - 1]
                        verified.append(
                            ClaimVerification(
                                claim=claim,
                                chunk_id=chunk_id,
                                category=category,
                                verdict=verdict,
                                reason="",
                            )
                        )
                    return
                for item in result.claims:
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

            collect(batch)

            # The verifier routinely returns fewer verdicts than it was sent -
            # measured runs came back with three verdicts for ten and for
            # fourteen claims, and the rest were being recorded as refuted.
            # Ask once more for only what it skipped, listing the indexes
            # explicitly so the request is small and unambiguous.
            outstanding = [
                index for index in range(1, len(valid_pairs) + 1)
                if index not in seen_indexes
            ]
            if outstanding:
                second_request_used = True
                # Only the blocks the skipped claims actually cite. Re-sending
                # every source cost ~7s of prefill to re-read premises that
                # already had verdicts.
                outstanding_pairs = [
                    (index, valid_pairs[index - 1]) for index in outstanding
                ]
                retry_items = _format_verification_items(
                    [pair for _, pair in outstanding_pairs],
                    hits_by_id,
                    start_index=0,
                    explicit_indexes=[index for index, _ in outstanding_pairs],
                )
                retry_prompt = (
                    "You returned no verdict for some claims. Return a verdict for "
                    "EVERY numbered claim below and nothing else. Return one "
                    "verdict per claim in the order shown as JSON: "
                    "{\"verdicts\":[\"yes\",\"partial\",\"no\"]}. Verify each "
                    "claim only against its own premise. Return no explanations.\n\n"
                    f"{retry_items}"
                )
                try:
                    second, retry_calls = await structured_with_metrics(
                        llm,
                        retry_prompt,
                        (
                            verdicts_for_exactly(len(outstanding))
                            if settings.verification_exact_verdict_grammar_enabled
                            else VerificationBatch
                        ),
                        num_predict=min(192, max(96, 64 + len(outstanding) * 12)),
                    )
                    llm_calls = [*llm_calls, *retry_calls]
                    # Retry numbering is explicit and can be sparse. Convert
                    # positional output back to the original claim indexes.
                    if second.verdicts:
                        second = VerificationBatch(
                            claims=[
                                VerdictItem(index=index, verdict=verdict)
                                for index, verdict in zip(
                                    outstanding,
                                    second.verdicts,
                                    strict=False,
                                )
                            ]
                        )
                    collect(second)
                except RuntimeError as exc:
                    llm_calls = [*llm_calls, *getattr(exc, "telemetry_metrics", [])]
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

    # A claim the verifier never ruled on is unknown, not refuted. Scoring the
    # two identically is what collapsed a well-grounded answer: three verdicts
    # returned for fourteen claims scored 3/14 = 0.214 against a 0.5 threshold,
    # so the graph abstained on an answer whose every adjudicated claim had
    # passed. Unadjudicated claims are excluded from the denominator and still
    # never published, because response generation publishes "yes" only. The
    # gate is unchanged for every claim that actually received a verdict.
    accounted = {(item.claim, item.chunk_id) for item in verified}
    unadjudicated = [
        (category, claim, chunk_id)
        for category, claim, chunk_id in valid_pairs
        if (claim, chunk_id) not in accounted
    ]
    for category, claim, chunk_id in unadjudicated:
        verified.append(
            ClaimVerification(
                claim=claim,
                chunk_id=chunk_id,
                category=category,
                verdict="no",
                reason="No verifier result",
            )
        )
    adjudicated = [
        item for item in verified if item.reason != "No verifier result"
    ]
    # Claims whose chunk ID was not retrieved stay in the denominator: those
    # are fabricated citations, and the answer should be penalised for them.
    total = max(len(adjudicated) + len(missing), 1)
    support = sum(
        1.0 if item.verdict == "yes" else 0.5 if item.verdict == "partial" else 0.0
        for item in adjudicated
    )
    score = 0.0 if not pairs or draft == INSUFFICIENT_EVIDENCE else support / total
    unsupported = missing + [
        item.claim for item in adjudicated if item.verdict == "no"
    ]
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
                "unadjudicated": len(unadjudicated),
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
            "truncated_premise_count": truncated_premise_count,
        },
        outputs={
            "verified_claim_count": len(verified),
            "unsupported_claim_count": len(result.unsupported_claims),
            "score": result.score,
            "fallback_used": fallback_used,
            "llm_skipped": not valid_pairs,
            "adjudicated_claim_count": len(adjudicated),
            "unadjudicated_claim_count": len(unadjudicated),
            "second_verification_request_used": second_request_used,
            "verdict_schema_exact_length": len(valid_pairs) if valid_pairs else 0,
        },
        llm_calls=llm_calls,
    )
    return {
        "verification_result": result,
        "agent_trace": trace,
        "stage_metrics": stage_metrics,
    }
