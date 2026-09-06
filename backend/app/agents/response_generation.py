from __future__ import annotations

import re
from time import perf_counter_ns

from app.schemas.agents import AgentCitation, AgentTraceEvent
from app.services.citation_status import citation_labels
from app.services.currency import CurrencyStatus, resolve_currency
from app.services.repeal_labels import repeal_notice
from app.services.section_confidence import section_confidence
from app.services.generation import INSUFFICIENT_EVIDENCE
from app.services.pipeline_telemetry import append_stage_metric, text_size


MARKER_RE = re.compile(r"\[SRC:([^\]]+)\]")
# The same five verified categories, named for what each role is actually
# reading for. A police officer reading "Practical next steps" reads advice;
# the BNSS imposes obligations, and "Required procedural steps" is what the
# section contains. An advocate needs the contrary case flagged as such, not
# filed under "uncertainties".
#
# These strings are load-bearing beyond the answer text: frontend/lib/
# answer-presentation.ts classifies sections by matching on the heading, so
# a label that matches none of its patterns silently falls into the generic
# body. test_section_labels.py pins the full set, and the frontend has a
# matching test, so a new label fails on both sides rather than degrading
# quietly on one.
CITIZEN_SECTION_LABELS = {
    "direct_answer": "Direct answer",
    "legal_basis": "Why this is the legal position",
    "application": "How this applies to you",
    "next_step": "What you can do now",
    "limit": "Important limits",
}

POLICE_SECTION_LABELS = {
    "direct_answer": "Direct answer",
    "legal_basis": "Governing provision and legal basis",
    "application": "Application to this matter",
    "next_step": "Required procedural steps",
    "limit": "Safeguards, limits and uncertainties",
}

ADVOCATE_SECTION_LABELS = {
    "direct_answer": "Direct answer",
    "legal_basis": "Authority and legal basis",
    "application": "Application to these facts",
    "next_step": "Steps available",
    "limit": "Contrary considerations, limits and gaps",
}

ROLE_SECTION_LABELS = {
    "citizen": CITIZEN_SECTION_LABELS,
    "police": POLICE_SECTION_LABELS,
    "advocate": ADVOCATE_SECTION_LABELS,
}

# Admin and any future role fall back to the citizen shape rather than to a
# professional one: plain language is the safe default for an unknown reader.
PROFESSIONAL_SECTION_LABELS = POLICE_SECTION_LABELS


def response_generation_node(state: dict) -> dict:
    started_ns = perf_counter_ns()
    result = state["verification_result"]
    hits = list(state.get("retrieved_chunks", []))
    hit_by_id = {str(hit.payload.get("chunk_id")): hit for hit in hits}
    section_grades: list[dict] = []
    if result.score < 0.5:
        answer = INSUFFICIENT_EVIDENCE
        cited_ids: list[str] = []
    else:
        # Rebuild the response from individually verified claim-marker pairs.
        # Removing whole lines is unsafe because one paragraph can contain both
        # supported and unsupported claims.
        role = str(state.get("role") or "citizen")
        section_labels = ROLE_SECTION_LABELS.get(role, CITIZEN_SECTION_LABELS)
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
            # Resolved rather than read. The stored flag is None for every
            # point in the live index, so `is True` never fired and this gate
            # has been open since the field was added.
            if hit is None or not resolve_currency(hit.payload).may_ground_a_published_claim:
                continue
            supported_sources.setdefault(key, [])
            if claim.chunk_id not in supported_sources[key]:
                supported_sources[key].append(claim.chunk_id)
        # Which sources ground each section, kept per category so each part
        # of the answer can be graded on what actually backs it. One number
        # for the whole answer hides the case this exists for: a governing
        # provision quoted from the Sanhita, followed by next steps drawn
        # from a single circular.
        sources_by_category: dict[str, list[str]] = {
            category: [] for category in section_labels
        }
        claims_by_category: dict[str, int] = {category: 0 for category in section_labels}
        for (category, claim), chunk_ids in supported_sources.items():
            markers = " ".join(f"[SRC:{chunk_id}]" for chunk_id in chunk_ids)
            supported_by_category[category].append(
                f"{claim.rstrip(' .')} {markers}."
            )
            claims_by_category[category] += 1
            for chunk_id in chunk_ids:
                if chunk_id not in sources_by_category[category]:
                    sources_by_category[category].append(chunk_id)
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
        payload_by_chunk_id = {
            chunk_id: hit.payload for chunk_id, hit in hit_by_id.items()
        }
        section_grades = [
            section_confidence(
                section_labels[category],
                sources_by_category[category],
                payload_by_chunk_id,
                claim_count=claims_by_category[category],
            ).as_row()
            # Only sections that were published. Grading an empty section
            # would put a "limited" row in front of the reader for something
            # the answer does not contain.
            for category in section_labels
            if supported_by_category[category]
        ]

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
        labels = citation_labels(payload)
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
                **labels,
            )
        )
    answer = MARKER_RE.sub(lambda match: f"[Source {number_by_id[match.group(1)]}]" if match.group(1) in number_by_id else "", answer)
    if answer != INSUFFICIENT_EVIDENCE:
        # Resolved, not read off `is_current`. That field is false for every
        # document in the corpus by design, so the old test reported "status
        # not verified" for a repealed Act we positively know was replaced --
        # the weakest of the three things this could say, on the one source
        # where the reader most needs the strongest.
        replaced: dict[str, str] = {}
        renumbered: dict[str, str] = {}
        not_re_enacted: set[str] = set()
        unverified = False
        for chunk_id in cited_ids:
            hit = hit_by_id.get(chunk_id)
            if hit is None or hit.payload.get("corpus_scope") == "private_case":
                continue
            decision = resolve_currency(hit.payload)
            if decision.status is CurrencyStatus.SUPERSEDED:
                name = hit.payload.get("act_name") or hit.payload.get("title") or "A cited Act"
                if decision.superseded_by:
                    replaced[str(name)] = decision.superseded_by
            elif decision.status is CurrencyStatus.UNVERIFIED:
                unverified = True

            # A judgment or circular is itself in force while the provision it
            # construes has moved. Without this the answer quotes "section 41
            # of the CrPC" from a 2025 judgment and never mentions that the
            # section is now BNSS s.35 -- the single most common currency
            # question in Indian law right now.
            notice = repeal_notice(hit.payload)
            for mapping in notice.mappings:
                key = f"{mapping.from_code} s.{mapping.from_section}"
                value = f"{mapping.to_code} s.{mapping.to_section}"
                if mapping.ingredients_changed:
                    value += " (the elements of the provision also changed)"
                renumbered[key] = value
            # A provision the new code dropped altogether. Saying nothing
            # here would leave the reader assuming it survived under a new
            # number, which is what happens with sedition: IPC s.124A was
            # not re-enacted, and BNS s.152 is a different offence.
            for reference in notice.not_re_enacted:
                not_re_enacted.add(reference)

        if replaced or renumbered or not_re_enacted or unverified:
            answer += "\n\n## Source currency\n\n"
        if replaced:
            lines = "\n".join(
                f"- **{name}** was replaced by {successor}. It still governs conduct from "
                "before that date, so it may be the right authority for an older matter, "
                "but not for anything happening now."
                for name, successor in sorted(replaced.items())
            )
            answer += (
                "One or more sources above is no longer in force:\n\n" + lines + "\n\n"
            )
        if renumbered:
            moved = "\n".join(
                f"- {old} is now {new}." for old, new in sorted(renumbered.items())
            )
            answer += (
                "The sources above remain in force, but they cite provisions that were "
                "renumbered when the 2023 Sanhitas commenced on 1 July 2024:\n\n"
                + moved
                + "\n\n"
            )
        if not_re_enacted:
            dropped = "\n".join(
                f"- {reference} was **not carried forward** into the replacing Act. "
                "It has no direct successor provision, so there is no renumbered "
                "equivalent to rely on."
                for reference in sorted(not_re_enacted)
            )
            answer += (
                "One or more provisions cited above were repealed without "
                "replacement:\n\n" + dropped + "\n\n"
            )
        if unverified:
            answer += (
                "The remaining cited material supports the statements above, but its "
                "current-law status is not verified in the corpus metadata. Check the "
                "latest official text and amendments before relying on it for a live "
                "matter."
                if replaced or renumbered
                else
                "The cited corpus material supports the statements above, but its "
                "current-law status is not verified in the corpus metadata. Check the "
                "latest official text and amendments before relying on it for a live "
                "matter."
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
        "section_confidence": section_grades,
        "citations": citations,
        "confidence_score": published_score,
        "evidence_strength": strength,
        "agent_trace": trace,
        "stage_metrics": stage_metrics,
    }
