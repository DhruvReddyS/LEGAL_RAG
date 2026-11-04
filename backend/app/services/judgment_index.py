"""What the corpus actually holds in judgments, read from the corpus at runtime.

Precedent research, the treatment check, the opponent check and case comparison
all answer from a small set of judgments. Against a small set those features
appear to work and can be wrong, so every result they return must say how many
judgments were searched, and that a judgment not found is not evidence that
none exists. The count is read from the index, because the corpus will grow and
a number written into the code would go on being printed after it stopped being
true.

The citation edges are the ingestion parser's `cited_cases` and
`cited_provisions`, which that parser documents as a retrieval hint and never
proof. OCR damages citations and the party-name pattern clips names at "of"
("Arnesh Kumar v. State"). So matching here is deliberately loose, says how it
matched, and everything built on it presents the passage for the advocate to
read rather than a conclusion.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from qdrant_client import models

GENERIC_PARTY_WORDS = frozenset(
    {
        "the", "of", "and", "anr", "another", "ors", "others", "etc", "by", "through", "thr",
        "mr", "mrs", "ms", "smt", "shri", "sri", "dr", "retd", "justice", "hon", "ble",
        "state", "union", "india", "govt", "government", "nct", "ut", "v", "vs",
        "appellant", "respondent", "petitioner", "accused", "ltd", "limited", "pvt", "co",
    }
)
_V = re.compile(r"\s+(?:vs?\.?|versus)\s+", re.IGNORECASE)
# "... vs K.AJITH Crl.A. No. 697/2021": the case number follows the second party.
_TRAILING_CASE_NUMBER = re.compile(r"\s+[\w.()/-]+\s+No\.?\s*\d.*$", re.IGNORECASE)
_CASE_NUMBER_WORDS = re.compile(
    r"\s+(?:crl|cri|criminal|civil|writ|w\.?p|c\.?a|slp|s\.?l\.?p|t\.?p|r\.?p|m\.?a|appeal|petition|diary|arb|contempt)\b.*$",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"[a-z0-9]+")

# Reported citation forms, as the ingestion parser normalises them.
REPORTED_CITATION = re.compile(
    r"\(\s*(?:19|20)\d{2}\s*\)\s*\d{1,3}\s*(?:SCC|SCR|SCALE|AIR)\s*\d{1,5}"
    r"|AIR\s*(?:19|20)\d{2}\s*(?:SC|SCC|Del|Bom|Mad|Cal|All|Ker|Kar)\s*\d{1,5}"
    r"|(?:19|20)\d{2}\s*INSC\s*\d{1,5}",
    re.IGNORECASE,
)
# Unlike the ingestion pattern, this allows "of", "the" and "&" inside a party,
# so "State of Kerala v. K. Ajith" keeps its first party whole.
_PARTY = r"[A-Z][\w.'()-]*(?:\s+(?:(?:of|the|for|and|&|in)\s+)?[A-Z][\w.'()-]*){0,7}"
CASE_NAME = re.compile(rf"(?P<first>{_PARTY})\s+(?:vs?\.?|versus|Vs\.?|V\.)\s+(?P<second>{_PARTY})")
_NOT_A_PARTY = frozenset({"in", "see", "and", "of", "at", "para", "supra", "the", "ors", "anr", "others"})


def normalise_citation(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def party_tokens(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in _TOKEN.findall(value.casefold())
        if token not in GENERIC_PARTY_WORDS and len(token) > 1
    )


def split_title(title: str) -> tuple[str, str] | None:
    parts = _V.split(title, maxsplit=1)
    if len(parts) != 2:
        return None
    second = _TRAILING_CASE_NUMBER.sub("", parts[1])
    second = _CASE_NUMBER_WORDS.sub("", second)
    return parts[0].strip(" .,"), second.strip(" .,")


@dataclass(frozen=True)
class PartyMatch:
    matched: bool
    confidence: str = ""  # likely | possible


def _side_compatible(query: frozenset[str], query_raw: str, title: frozenset[str], title_raw: str) -> tuple[bool, int]:
    if query:
        shared = query & title
        return (bool(shared) and (query <= title or title <= query)), len(shared)
    # "Union of India" or a clipped "State" has no distinctive word to compare.
    raw_query = set(_TOKEN.findall(query_raw.casefold()))
    raw_title = set(_TOKEN.findall(title_raw.casefold()))
    return bool(raw_query & raw_title), 0


def match_parties(first: str, second: str, title_first: str, title_second: str) -> PartyMatch:
    """Whether a reference's parties could be this judgment's, in either order.

    Needs a distinctive word to match: every "State v. Union of India" would
    otherwise match every other. Two distinctive words, or one on each side,
    reads as likely; one alone may be a common name and reads as possible.
    """
    qa, qb = party_tokens(first), party_tokens(second)
    ta, tb = party_tokens(title_first), party_tokens(title_second)
    best = PartyMatch(False)
    for (left, left_raw), (right, right_raw) in (
        ((ta, title_first), (tb, title_second)),
        ((tb, title_second), (ta, title_first)),
    ):
        ok_a, count_a = _side_compatible(qa, first, left, left_raw)
        ok_b, count_b = _side_compatible(qb, second, right, right_raw)
        if not (ok_a and ok_b) or count_a + count_b == 0:
            continue
        confidence = "likely" if count_a + count_b >= 2 else "possible"
        if not best.matched or confidence == "likely":
            best = PartyMatch(True, confidence)
    return best


@dataclass(frozen=True)
class ChunkEdge:
    point_id: Any
    chunk_id: str
    page_start: int
    page_end: int
    cited_cases: tuple[str, ...]
    cited_provisions: tuple[str, ...]


@dataclass
class HeldJudgment:
    document_id: str
    title: str
    court: str
    decision_year: int | None
    decision_date: str | None
    source_url: str | None
    chunks: list[ChunkEdge] = field(default_factory=list)

    @property
    def parties(self) -> tuple[str, str] | None:
        return split_title(self.title)

    def summary(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "court": self.court,
            "decision_year": self.decision_year,
            "decision_date": self.decision_date,
            "source_url": self.source_url,
        }

    def self_citations(self) -> set[str]:
        """Citations on the judgment's first page, where it usually states its own."""
        first_page = min((chunk.page_start for chunk in self.chunks), default=1)
        return {
            normalise_citation(case)
            for chunk in self.chunks
            if chunk.page_start == first_page
            for case in chunk.cited_cases
            if REPORTED_CITATION.fullmatch(case.strip())
        }


@dataclass(frozen=True)
class Coverage:
    judgments_held: int
    by_court: dict[str, int]
    year_min: int | None
    year_max: int | None
    undated: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "judgments_held": self.judgments_held,
            "by_court": self.by_court,
            "year_min": self.year_min,
            "year_max": self.year_max,
            "undated": self.undated,
        }


ABSENCE_NOTE = "A judgment not found here is not evidence that none exists."


def coverage_statement(
    coverage: Coverage | None,
    *,
    judgments_searched: int | None = None,
    what: str = "Searched",
) -> dict[str, Any]:
    """The sentence every judgment-based result must carry.

    An unreadable count stays unknown. Falling back to a remembered number is
    the failure this module exists to prevent.
    """
    if coverage is None:
        return {
            "judgments_held": None,
            "judgments_searched": None,
            "by_court": {},
            "statement": "The number of judgments held could not be read, so the scope of this result is unknown.",
            "absence_note": ABSENCE_NOTE,
        }
    searched = coverage.judgments_held if judgments_searched is None else judgments_searched
    courts = ", ".join(f"{count} {court}" for court, count in sorted(coverage.by_court.items()))
    scope = (
        f"{what} {searched} of the {coverage.judgments_held} judgments this corpus holds"
        if searched != coverage.judgments_held
        else f"{what} the {coverage.judgments_held} judgments this corpus holds"
    )
    return {
        "judgments_held": coverage.judgments_held,
        "judgments_searched": searched,
        "by_court": coverage.by_court,
        "statement": f"{scope} ({courts}). This is a small collection, not the reported case law of India.",
        "absence_note": ABSENCE_NOTE,
    }


_EDGE_FIELDS = [
    "canonical_document_id", "document_id", "title", "case_title", "court", "decision_year",
    "decision_date", "source_url", "chunk_id", "page_start", "page_end", "cited_cases", "cited_provisions",
]


class CorpusUnavailable(RuntimeError):
    """The index could not be read. Reported, never answered from memory."""


class JudgmentIndex:
    """Every judgment held, built by scrolling the served collection.

    Text is not loaded: the edges fit comfortably, and passages are
    fetched by id when a result needs them. Cached briefly, so the count can
    follow a corpus update without a restart.
    """

    def __init__(self, client: Any, collection: str, *, ttl_seconds: float = 300.0) -> None:
        self.client = client
        self.collection = collection
        self.ttl_seconds = ttl_seconds
        self._built_at = 0.0
        self._judgments: dict[str, HeldJudgment] | None = None
        self._lock = asyncio.Lock()

    def _filter(self, *extra: models.Condition) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(key="source_type", match=models.MatchValue(value="judgment")),
                # The same tiers served retrieval reads, so noise held back
                # from answers is not counted as searched.
                models.FieldCondition(key="corpus_tier", match=models.MatchAny(any=["gold", "extended"])),
                *extra,
            ]
        )

    async def _scroll_all(self, scroll_filter: models.Filter, payload: list[str] | bool) -> list[Any]:
        records: list[Any] = []
        offset: Any = None
        try:
            while True:
                batch, offset = await self.client.scroll(
                    collection_name=self.collection,
                    scroll_filter=scroll_filter,
                    limit=256,
                    offset=offset,
                    with_payload=payload,
                    with_vectors=False,
                )
                records.extend(batch)
                if offset is None:
                    return records
        except Exception as exc:
            raise CorpusUnavailable("the judgment index could not be read") from exc

    async def judgments(self) -> dict[str, HeldJudgment]:
        async with self._lock:
            if self._judgments is not None and time.monotonic() - self._built_at < self.ttl_seconds:
                return self._judgments
            records = await self._scroll_all(self._filter(), _EDGE_FIELDS)
            built: dict[str, HeldJudgment] = {}
            for record in records:
                payload = dict(record.payload or {})
                document_id = str(payload.get("canonical_document_id") or payload.get("document_id") or "")
                if not document_id:
                    continue
                year = payload.get("decision_year")
                held = built.setdefault(
                    document_id,
                    HeldJudgment(
                        document_id=document_id,
                        title=str(payload.get("case_title") or payload.get("title") or "Untitled judgment"),
                        court=str(payload.get("court") or "Court not recorded"),
                        decision_year=int(year) if year else None,
                        decision_date=(str(payload["decision_date"])[:10] if payload.get("decision_date") else None),
                        source_url=payload.get("source_url") or None,
                    ),
                )
                held.chunks.append(
                    ChunkEdge(
                        point_id=record.id,
                        chunk_id=str(payload.get("chunk_id") or record.id),
                        page_start=int(payload.get("page_start") or 1),
                        page_end=int(payload.get("page_end") or payload.get("page_start") or 1),
                        cited_cases=tuple(str(item) for item in payload.get("cited_cases") or ()),
                        cited_provisions=tuple(str(item) for item in payload.get("cited_provisions") or ()),
                    )
                )
            for held in built.values():
                held.chunks.sort(key=lambda chunk: (chunk.page_start, chunk.chunk_id))
            self._judgments = built
            self._built_at = time.monotonic()
            return built

    async def coverage(self) -> Coverage | None:
        """None when unreadable. Callers print that as unknown scope."""
        try:
            judgments = await self.judgments()
        except CorpusUnavailable:
            return None
        return coverage_of(judgments.values())

    async def fetch_chunks(self, point_ids: Iterable[Any]) -> dict[Any, dict[str, Any]]:
        ids = list(point_ids)
        if not ids:
            return {}
        try:
            records = await self.client.retrieve(
                collection_name=self.collection, ids=ids, with_payload=True, with_vectors=False
            )
        except Exception as exc:
            raise CorpusUnavailable("passages could not be read") from exc
        return {record.id: dict(record.payload or {}) for record in records}

    async def document_chunks(self, document_id: str) -> list[dict[str, Any]]:
        """A judgment's passages in page order, or nothing if it is not held."""
        records = await self._scroll_all(
            self._filter(
                models.FieldCondition(
                    key="canonical_document_id", match=models.MatchValue(value=document_id)
                )
            ),
            True,
        )
        payloads = [dict(record.payload or {}) for record in records]
        payloads.sort(key=lambda item: (int(item.get("page_start") or 0), str(item.get("chunk_id") or "")))
        return payloads


def coverage_of(judgments: Iterable[HeldJudgment]) -> Coverage:
    items = list(judgments)
    years = [item.decision_year for item in items if item.decision_year]
    return Coverage(
        judgments_held=len(items),
        by_court=dict(Counter(item.court for item in items)),
        year_min=min(years) if years else None,
        year_max=max(years) if years else None,
        undated=sum(1 for item in items if not item.decision_year),
    )


@dataclass(frozen=True)
class CaseReference:
    raw: str
    first: str | None = None
    second: str | None = None
    citation: str | None = None
    context: str = ""


_NEAR = 80


def _sentence_around(text: str, start: int, end: int) -> str:
    left = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start))
    right_candidates = [pos for pos in (text.find(". ", end), text.find("\n", end)) if pos != -1]
    right = min(right_candidates) if right_candidates else len(text)
    return " ".join(text[left + 1 : right + 1].split())[:600]


def parse_case_references(text: str, *, limit: int = 40) -> list[CaseReference]:
    """Case citations in free text, pairing a name with a citation beside it.

    Written for a pasted filing, where "State of Kerala v. K. Ajith, (2022) 3
    SCC 1" should be one reference with both parts, not two rows.
    """
    text = text or ""
    found: list[CaseReference] = []
    used_citations: set[tuple[int, int]] = set()
    citations = [(m.start(), m.end(), " ".join(m.group(0).split())) for m in REPORTED_CITATION.finditer(text)]
    for match in CASE_NAME.finditer(text):
        first = match.group("first").strip()
        second = match.group("second").strip(" .,")
        if first.split()[0].casefold().strip(".,") in _NOT_A_PARTY:
            words = first.split()
            while words and words[0].casefold().strip(".,") in _NOT_A_PARTY:
                words.pop(0)
            first = " ".join(words)
        if not first or not (party_tokens(first) or party_tokens(second)):
            continue
        citation = None
        for span_start, span_end, value in citations:
            if 0 <= span_start - match.end() <= _NEAR or 0 <= match.start() - span_end <= _NEAR:
                citation = value
                used_citations.add((span_start, span_end))
                break
        found.append(
            CaseReference(
                raw=f"{first} v. {second}" + (f", {citation}" if citation else ""),
                first=first,
                second=second,
                citation=citation,
                context=_sentence_around(text, match.start(), match.end()),
            )
        )
    for span_start, span_end, value in citations:
        if (span_start, span_end) not in used_citations:
            found.append(CaseReference(raw=value, citation=value, context=_sentence_around(text, span_start, span_end)))
    seen: set[str] = set()
    unique: list[CaseReference] = []
    for reference in sorted(found, key=lambda item: text.find(item.first or item.raw)):
        key = reference.raw.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(reference)
    return unique[:limit]


def find_held(reference: CaseReference, judgments: dict[str, HeldJudgment]) -> list[dict[str, Any]]:
    """Judgments held that this reference could mean, with how it matched.

    More than one candidate comes back as more than one, because choosing is
    the advocate's call.
    """
    results: list[dict[str, Any]] = []
    citation = normalise_citation(reference.citation) if reference.citation else None
    for held in judgments.values():
        if citation and citation in held.self_citations():
            results.append(
                {**held.summary(), "match_basis": "citation", "confidence": "likely",
                 "match_note": "This citation appears on the judgment's first page."}
            )
            continue
        parties = held.parties
        if reference.first and reference.second and parties:
            match = match_parties(reference.first, reference.second, parties[0], parties[1])
            if match.matched:
                results.append(
                    {**held.summary(), "match_basis": "party_names", "confidence": match.confidence,
                     "match_note": "Matched on party names in the title. Confirm it is the same judgment."}
                )
    results.sort(key=lambda item: item["confidence"] != "likely")
    return results


def _reference_from_edge(edge: str) -> CaseReference:
    edge = edge.strip()
    if REPORTED_CITATION.fullmatch(edge):
        return CaseReference(raw=edge, citation=edge)
    parts = _V.split(edge, maxsplit=1)
    if len(parts) == 2:
        return CaseReference(raw=edge, first=parts[0].strip(), second=parts[1].strip(" ."))
    return CaseReference(raw=edge)


def edge_matches(edge: str, *, parties: tuple[str, str] | None, citations: set[str]) -> bool:
    """Whether one stored `cited_cases` entry points at the judgment asked about."""
    reference = _reference_from_edge(edge)
    if reference.citation:
        return normalise_citation(reference.citation) in citations
    if reference.first and reference.second and parties:
        return match_parties(reference.first, reference.second, parties[0], parties[1]).matched
    return False
