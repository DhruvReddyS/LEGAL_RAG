from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Case, GeneratedDocument
from app.schemas.documents import DraftAuthority, FIRFacts
from app.services.llm import OllamaClient
from app.services.retrieval import HybridRetrievalService, RetrievalFilters


FIR_REQUIRED_FIELDS = (
    "complainant_name",
    "incident_date",
    "incident_location",
    "subject_or_property",
)

PROFESSIONAL_REVIEW_DISCLAIMER = (
    "DRAFT FOR REVIEW — This is decision-support, not a filed FIR or legal advice. "
    "Verify every fact, date, identity, jurisdiction and proposed legal provision with "
    "the complainant and the responsible police/legal professional before submission."
)


def missing_fir_fields(facts: FIRFacts) -> list[str]:
    return [field for field in FIR_REQUIRED_FIELDS if not getattr(facts, field)]


def recover_explicit_missing_item(facts: FIRFacts, description: str) -> FIRFacts:
    """Copy narrow, explicit missing-item text when structured extraction omits it."""
    updates: dict[str, object] = {}
    if not facts.subject_or_property:
        match = re.search(
            r"\bmy\s+(.{2,120}?)\s+(?:went\s+missing|has\s+gone\s+missing|is\s+missing)\b",
            description,
            flags=re.IGNORECASE,
        )
        if match:
            subject = re.sub(
                r",?\s*collar(?:\s+number)?\s+[A-Za-z0-9-]+,?\s*$",
                "",
                match.group(1).strip(" ,.;"),
                flags=re.IGNORECASE,
            ).strip(" ,.;")
            if subject:
                updates["subject_or_property"] = subject
    collar = re.search(
        r"\bcollar(?:\s+number)?\s+([A-Za-z0-9-]+)",
        description,
        flags=re.IGNORECASE,
    )
    if collar and not any(collar.group(1).casefold() in item.casefold() for item in facts.identification_details):
        updates["identification_details"] = [
            *facts.identification_details,
            f"Collar number {collar.group(1)}",
        ]
    return facts.model_copy(update=updates) if updates else facts


def render_fir(facts: FIRFacts, authorities: list[DraftAuthority]) -> str:
    def value(item: str | None) -> str:
        return item.strip() if item and item.strip() else "[INFORMATION REQUIRED]"

    witness_text = "; ".join(facts.witness_details) or "[INFORMATION REQUIRED, IF ANY]"
    identification = "; ".join(facts.identification_details) or "[INFORMATION REQUIRED]"
    authority_lines = (
        "\n".join(
            f"- {item.title}, section {item.section or 'not identified'}, "
            f"pages {item.page_start}-{item.page_end} [SRC:{item.chunk_id}]"
            for item in authorities
        )
        or "- No sufficiently relevant corpus authority was retrieved; do not insert a section without review."
    )
    return f"""{PROFESSIONAL_REVIEW_DISCLAIMER}

TO
The Station House Officer
[POLICE STATION AND DISTRICT REQUIRED]

SUBJECT
Complaint concerning {value(facts.subject_or_property)}

COMPLAINANT
Name: {value(facts.complainant_name)}
Contact/address: {value(facts.complainant_contact)}

INCIDENT
Date: {value(facts.incident_date)}
Time: {value(facts.incident_time)}
Location: {value(facts.incident_location)}

IDENTIFICATION / PROPERTY DETAILS
{identification}

PERSONS SEEN / SUSPECT DETAILS
{value(facts.suspect_details)}

REPORTED CIRCUMSTANCES / POSSIBLE OFFENCE
{value(facts.suspected_offence_or_circumstance)}

WITNESSES
{witness_text}

FACTUAL NARRATIVE
{value(facts.narrative)}

REQUESTED ACTION
{value(facts.requested_action)}

POSSIBLE LEGAL AUTHORITIES FOR PROFESSIONAL REVIEW
{authority_lines}

DECLARATION
I state that the factual information above is true to the best of my knowledge and belief.

Date/signature: [INFORMATION REQUIRED]
""".strip()


class LegalDraftingAgent:
    def __init__(
        self,
        *,
        session: AsyncSession,
        retrieval: HybridRetrievalService,
        llm: OllamaClient,
    ) -> None:
        self.session = session
        self.retrieval = retrieval
        self.llm = llm

    async def _extract_facts(self, description: str) -> FIRFacts:
        prompt = f"""Extract only explicitly supplied facts for an Indian police complaint/FIR draft.
Return JSON matching the schema. Never infer a name, date, time, place, suspect, offence, or legal
section. Use null or an empty list when absent. Keep the narrative factual and preserve uncertainty.

USER DESCRIPTION:
{description}"""
        try:
            return await self.llm.structured(prompt, FIRFacts)
        except RuntimeError:
            return FIRFacts(narrative=description)

    async def create_fir_draft(
        self, *, case: Case, description: str
    ) -> tuple[GeneratedDocument, FIRFacts, list[str], list[DraftAuthority], str]:
        # Lock the case row so concurrent saves cannot choose the same immutable version.
        await self.session.scalar(select(Case).where(Case.id == case.id).with_for_update())
        facts = recover_explicit_missing_item(
            await self._extract_facts(description), description
        )
        search_query = (
            "Indian law police complaint FIR registration cognizable offence missing property "
            f"{facts.suspected_offence_or_circumstance or ''} {facts.narrative}"
        )[:4000]
        hits = await self.retrieval.search(
            search_query,
            # Gold currently has no provision whose official consolidation has
            # been curated as current. Retrieve verified Gold evidence but keep
            # the mandatory professional currency warning in the draft.
            filters=RetrievalFilters(current_only=False, corpus_tiers=["gold", "extended"]),
            candidate_limit=20,
            result_limit=5,
        )
        authorities = [
            DraftAuthority(
                chunk_id=str(hit.payload.get("chunk_id")),
                title=str(hit.payload.get("title") or "Unknown authority"),
                section=str(hit.payload.get("section") or "") or None,
                page_start=int(hit.payload.get("page_start") or 1),
                page_end=int(hit.payload.get("page_end") or hit.payload.get("page_start") or 1),
                excerpt=str(hit.payload.get("text") or "")[:1200],
                reranker_score=float(hit.reranker_score),
            )
            for hit in hits
            if hit.payload.get("chunk_id") and hit.payload.get("text")
        ]
        missing = missing_fir_fields(facts)
        rendered = render_fir(facts, authorities)
        latest = await self.session.scalar(
            select(func.max(GeneratedDocument.version)).where(
                GeneratedDocument.case_id == case.id,
                GeneratedDocument.doc_type == "fir",
            )
        )
        version = int(latest or 0) + 1
        generated = GeneratedDocument(
            case_id=case.id,
            doc_type="fir",
            version=version,
            status="incomplete" if missing else "draft",
            content={
                "facts": facts.model_dump(mode="json"),
                "missing_fields": missing,
                "authorities": [item.model_dump(mode="json") for item in authorities],
                "rendered_text": rendered,
                "disclaimer": PROFESSIONAL_REVIEW_DISCLAIMER,
            },
        )
        self.session.add(generated)
        await self.session.flush()
        return generated, facts, missing, authorities, rendered
