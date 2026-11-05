"""Open a provision by its citation, with no model and no ranking.

Someone who already knows the citation should not wait for an answer or get the
nearest match. "IPC 420" is a request to read that section, and what it became.
So this is an exact filter on the corpus plus the official concordance: if the
provision is not held it says so, rather than offering a nearby number.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from qdrant_client import models

from app.core.config import settings
from app.services.currency import CurrencyStatus, resolve_currency
from app.services.quarantine import is_quarantined
from app.services.section_mapping import map_sections, resolve_code

# Every Act has a section 35, so this is the whole corpus's use of one number.
MAX_SECTION_CHUNKS = 5000
MAX_DOCUMENTS = 3

_NUMBER = r"(\d{1,4}[A-Z]{0,3}(?:\s?\(\s?\w{1,4}\s?\))*)"
_SECTION_WORD = r"(?:sections?|secs?\.?|ss?\.|articles?|arts?\.?|§)"
_SECTION_FIRST = re.compile(
    rf"^{_SECTION_WORD}\s*{_NUMBER}\s*(?:,|of\b|under\b|in\b)?\s*(?:the\s+)?(.*)$", re.IGNORECASE
)
_ACT_FIRST = re.compile(rf"^(.+?)[\s,]+(?:{_SECTION_WORD}\s*)?{_NUMBER}$", re.IGNORECASE)
_ARTICLE = re.compile(r"^(?:articles?|arts?\.?)\b", re.IGNORECASE)

# The words corpus titles use, for the shorthand people type.
_ACT_TEXT: dict[str, str] = {
    "IPC": "Indian Penal Code",
    "CrPC": "Code of Criminal Procedure",
    "IEA": "Indian Evidence Act",
    "BNS": "Bharatiya Nyaya Sanhita",
    "BNSS": "Bharatiya Nagarik Suraksha Sanhita",
    "BSA": "Bharatiya Sakshya Adhiniyam",
}
# Names only: the short forms in common use, for Acts cited by initials.
_SHORT_NAMES: dict[str, str] = {
    "cpa": "Consumer Protection Act",
    "cpc": "Code of Civil Procedure",
    "dv act": "Protection of Women from Domestic Violence Act",
    "it act": "Information Technology Act",
    "mv act": "Motor Vehicles Act",
    "ndps": "Narcotic Drugs and Psychotropic Substances Act",
    "ndps act": "Narcotic Drugs and Psychotropic Substances Act",
    "ni act": "Negotiable Instruments Act",
    "pmla": "Prevention of Money-Laundering Act",
    "pocso": "Protection of Children from Sexual Offences Act",
    "pocso act": "Protection of Children from Sexual Offences Act",
    "posh act": "Sexual Harassment of Women at Workplace",
    "rti act": "Right to Information Act",
    "sc/st act": "Scheduled Castes and the Scheduled Tribes",
    "uapa": "Unlawful Activities (Prevention) Act",
}
CONSTITUTION = "Constitution of India"
_WORD = re.compile(r"[a-z0-9]+")
_YEAR = re.compile(r"\b(?:18|19|20)\d{2}\b")


@dataclass(frozen=True)
class Citation:
    act: str
    section: str
    code: str | None = None

    @property
    def base_section(self) -> str:
        return self.section.split("(", 1)[0]


def parse_citation(text: str) -> Citation | None:
    """"IPC 420", "s.103 BNS", "Section 35(3) of the BNSS", "Article 21"."""
    cleaned = " ".join(text.strip().rstrip(".?").split())
    if not cleaned or len(cleaned) > 160:
        return None
    match = _SECTION_FIRST.match(cleaned)
    if match:
        number, act = match.group(1), match.group(2)
    else:
        match = _ACT_FIRST.match(cleaned)
        if not match:
            return None
        act, number = match.group(1), match.group(2)
    # A bare year is not a section: "Consumer Protection Act 2019" names no provision.
    if not _SECTION_FIRST.match(cleaned) and _YEAR.fullmatch(number) and not re.search(
        _SECTION_WORD, cleaned, re.IGNORECASE
    ):
        return None
    section = re.sub(r"\s", "", number).upper()
    act = act.strip(" ,")
    if _ARTICLE.match(cleaned) and not act:
        act = CONSTITUTION
    if not act:
        return None
    code = resolve_code(act) if len(act) > 3 or act.upper() != act else None
    code = code or _code_from_shorthand(act)
    if code and code in _ACT_TEXT:
        return Citation(act=_ACT_TEXT[code], section=section, code=code)
    return Citation(act=_SHORT_NAMES.get(act.casefold(), act), section=section, code=code)


def _code_from_shorthand(act: str) -> str | None:
    wanted = act.casefold().replace(".", "").replace(" ", "")
    return next((code for code in _ACT_TEXT if code.casefold() == wanted), None)


def _ranked(document: dict[str, Any]) -> tuple:
    first = document["payload"]
    decision = document["currency"]
    return (
        str(first.get("document_type")) == "bare_act",
        decision.status is not CurrencyStatus.SUPERSEDED,
        str(first.get("verified_official")).casefold() == "true",
        # A circular titled "Implementation of s.479 of the BNSS" names the Act
        # too. The shortest title is the Act itself.
        -len(_WORD.findall(str(first.get("act_name")).casefold())),
        len(document["text"]),
    )


def _documents_from(points: list[Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for point in points:
        payload = dict(point.payload or {})
        document = str(payload.get("canonical_document_id") or payload.get("document_id") or point.id)
        if not is_quarantined(document):
            grouped.setdefault(document, []).append(payload)
    documents = []
    for document_id, chunks in grouped.items():
        ordered = sorted(
            chunks,
            key=lambda item: (
                int(item.get("page_start") or 0),
                int(item.get("unit_ordinal") or 0),
                str(item.get("chunk_id")),
            ),
        )
        documents.append(
            {
                "id": document_id,
                "payload": ordered[0],
                "text": "\n\n".join(str(chunk.get("text") or "").strip() for chunk in ordered).strip(),
                "page_start": int(ordered[0].get("page_start") or 1),
                "page_end": max(int(chunk.get("page_end") or chunk.get("page_start") or 1) for chunk in ordered),
                "currency": resolve_currency(ordered[0]),
            }
        )
    documents.sort(key=_ranked, reverse=True)
    # With the Act in hand, a report that merely has a matching heading is noise.
    if documents and str(documents[0]["payload"].get("document_type")) == "bare_act":
        documents = [d for d in documents if str(d["payload"].get("document_type")) == "bare_act"]
    return documents[:MAX_DOCUMENTS]


_CLEAN_SECTION = re.compile(r"^\d+[A-Z]*(?:\(\w+\))*")


def _distinct_counterparts(mappings: tuple) -> list[dict[str, Any]]:
    """One row per target. The printed concordance repeats them per sub-section."""
    rows: dict[tuple[str, str | None], dict[str, Any]] = {}
    for mapping in mappings:
        found = _CLEAN_SECTION.match(mapping.to_section or "")
        to_section = found.group(0) if found else None
        if mapping.to_section and to_section is None:
            continue
        row = rows.setdefault(
            (mapping.to_code, to_section),
            {
                "from_code": mapping.from_code,
                "from_section": mapping.from_section,
                "to_code": mapping.to_code,
                "to_section": to_section,
                "subject": mapping.subject.strip(),
                "ingredients_changed": mapping.ingredients_changed,
                "note": mapping.note or None,
            },
        )
        row["subject"] = row["subject"] or mapping.subject.strip()
        row["ingredients_changed"] = row["ingredients_changed"] or mapping.ingredients_changed
    return list(rows.values())


def _names_the_act(act_name: object, act: str) -> bool:
    """All the words asked for are in the title. The store's text match is case-sensitive."""
    wanted = set(_WORD.findall(act.casefold())) - {"the", "of", "and"}
    return bool(wanted) and wanted <= set(_WORD.findall(str(act_name).casefold()))


async def lookup_provision(client: Any, query: str, *, collection: str | None = None) -> dict[str, Any]:
    citation = parse_citation(query)
    if citation is None:
        return {"query": query, "understood": False, "act": None, "section": None, "provisions": [], "counterparts": []}

    target = collection or settings.qdrant_global_collection
    candidates, _ = await client.scroll(
        collection_name=target,
        scroll_filter=models.Filter(
            must=[models.FieldCondition(key="section", match=models.MatchValue(value=citation.base_section))]
        ),
        limit=MAX_SECTION_CHUNKS,
        with_payload=["act_name"],
        with_vectors=False,
    )
    wanted = [point.id for point in candidates if _names_the_act((point.payload or {}).get("act_name"), citation.act)]
    points = (
        await client.retrieve(collection_name=target, ids=wanted, with_payload=True, with_vectors=False)
        if wanted
        else []
    )
    documents = await asyncio.to_thread(_documents_from, points)
    counterparts = map_sections(citation.code, citation.section) if citation.code else ()
    return {
        "query": query,
        "understood": True,
        "act": citation.act,
        "section": citation.section,
        "provisions": [
            {
                "title": str(document["payload"].get("title") or citation.act),
                "act_name": str(document["payload"].get("act_name") or citation.act),
                "section": str(document["payload"].get("section") or citation.base_section),
                "text": document["text"],
                "page_start": document["page_start"],
                "page_end": document["page_end"],
                "source_url": document["payload"].get("source_url") or None,
                "jurisdiction": document["payload"].get("jurisdiction") or None,
                "currency_status": document["currency"].status.value,
                "superseded_by": document["currency"].superseded_by,
                "currency_basis": document["currency"].basis or None,
            }
            for document in documents
        ],
        "counterparts": _distinct_counterparts(counterparts),
    }
