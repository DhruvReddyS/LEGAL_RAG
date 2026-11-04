"""Precedent search, the treatment check and the opponent check. No model.

All three return passages as they appear in the corpus, plus what a parser found
in them. None writes a sentence about what the law is, because against a small
judgment set an authored conclusion reads as a finding about the law when it is
only a finding about this collection.
"""

from __future__ import annotations

import re
from typing import Any

from app.ingestion.citations import extract_references
from app.services.authority_check import _CODE_BY_KEY, _check_one, check_authorities
from app.services.advocate_sources import source_from_payload
from app.services.judgment_index import (
    CaseReference,
    CorpusUnavailable,
    HeldJudgment,
    JudgmentIndex,
    coverage_of,
    coverage_statement,
    edge_matches,
    find_held,
    normalise_citation,
    parse_case_references,
    party_tokens,
)
from app.services.retrieval import HybridRetrievalService, RetrievalFilters

MAX_PRECEDENT_PASSAGES = 12
MAX_PASSAGES_PER_JUDGMENT = 3
_HOLDING_LANGUAGE = re.compile(
    r"[^.\n]*\b(?:we hold|it is held|held that|we are of the (?:considered )?(?:view|opinion)|"
    r"we conclude|we answer|the question is answered|it is declared)\b[^.\n]*\.",
    re.IGNORECASE,
)

# Words read from a passage beside a reference. Nothing here decides what the
# later court did: "overruled" may describe a third case, and "followed" may sit
# in a sentence about a different point.
TREATMENT_WORDS: tuple[tuple[str, str, bool], ...] = (
    ("overruled", r"over-?ruled|over-?ruling", True),
    ("per incuriam", r"per\s+incuriam", True),
    ("doubted", r"\bdoubted\b", True),
    ("reversed", r"\breversed\b", True),
    ("set aside", r"\bset\s+aside\b", True),
    ("referred to a larger bench", r"larger\s+bench", True),
    ("reconsidered", r"\breconsider", True),
    ("distinguished", r"\bdistinguish", False),
    ("followed", r"\bfollowed\b", False),
    ("affirmed", r"\baffirmed\b", False),
    ("relied on", r"\brelied\s+(?:up)?on\b", False),
    ("upheld", r"\bupheld\b", False),
)
_WINDOW = 320

TREATMENT_LABEL = "Partial check of held material. This is not a citator."
TREATMENT_LIMITS = (
    "This corpus holds no overruling or subsequent-history data. Later treatment outside the "
    "judgments held is invisible here.",
    "Citation edges are parsed from text and can be wrong or missing. An absent edge does not mean "
    "a judgment was not cited.",
    "Words beside a reference are shown for you to read in context. They are not a finding on how "
    "the later court treated it.",
    "Check a full citator before relying on any judgment.",
)
OPPONENT_LIMITS = (
    "Provisions are checked against the official concordance only. Others are listed as not checked.",
    "A held passage is shown for you to read. Whether it supports the proposition is not decided here.",
)


def holding_sentences(text: str, *, limit: int = 2) -> list[str]:
    """Sentences using the language of a holding, verbatim. Not the ratio."""
    return [" ".join(match.group(0).split())[:500] for match in _HOLDING_LANGUAGE.finditer(text)][:limit]


def _in_scope(judgments: dict[str, HeldJudgment], court: str | None, year_from: int | None, year_to: int | None) -> list[HeldJudgment]:
    def keep(item: HeldJudgment) -> bool:
        if court and item.court != court:
            return False
        if year_from is not None or year_to is not None:
            if item.decision_year is None:
                return False
            if year_from is not None and item.decision_year < year_from:
                return False
            if year_to is not None and item.decision_year > year_to:
                return False
        return True

    return [item for item in judgments.values() if keep(item)]


async def search_precedents(
    *,
    retrieval: HybridRetrievalService,
    index: JudgmentIndex,
    query: str,
    holding: str | None = None,
    court: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> dict[str, Any]:
    """Passages from the judgments held, grouped by judgment, ranked by retrieval."""
    coverage = await index.coverage()
    scope_note = ""
    searched: int | None = None
    if coverage is not None:
        judgments = await index.judgments()
        scoped = _in_scope(judgments, court, year_from, year_to)
        searched = len(scoped)
        if (year_from is not None or year_to is not None) and coverage.undated:
            scope_note = (
                f"{coverage.undated} judgment(s) have no decision year recorded and a year filter "
                "excludes them."
            )
    text = " ".join(part for part in (query, holding) if part)[:4000]
    hits = await retrieval.search(
        text,
        filters=RetrievalFilters(
            source_types=["judgment"],
            courts=[court] if court else [],
            year_from=year_from,
            year_to=year_to,
        ),
        candidate_limit=40,
        result_limit=MAX_PRECEDENT_PASSAGES,
    )
    grouped: dict[str, dict[str, Any]] = {}
    for hit in hits:
        payload = hit.payload
        document_id = str(payload.get("canonical_document_id") or payload.get("document_id") or payload.get("chunk_id"))
        group = grouped.setdefault(
            document_id,
            {
                "document_id": document_id,
                "title": str(payload.get("case_title") or payload.get("title") or "Untitled"),
                "court": payload.get("court") or None,
                "decision_year": payload.get("decision_year") or None,
                "decision_date": str(payload["decision_date"])[:10] if payload.get("decision_date") else None,
                "source_url": payload.get("source_url") or None,
                "passages": [],
            },
        )
        if len(group["passages"]) >= MAX_PASSAGES_PER_JUDGMENT:
            continue
        group["passages"].append(
            {
                "source": source_from_payload(payload, score=float(hit.reranker_score)),
                "holding_language": holding_sentences(str(payload.get("text") or "")),
            }
        )
    results = list(grouped.values())
    return {
        "coverage": coverage_statement(coverage, judgments_searched=searched),
        "scope_note": scope_note,
        "results": results,
        "empty_note": (
            ""
            if results
            else "Nothing matched in the judgments held. That says nothing about whether such a judgment exists."
        ),
        "method": (
            "Passages are shown as they appear in the judgment, unsummarised. Sentences marked as "
            "holding language were found by wording alone and are not a statement of the ratio."
        ),
    }


def _treatment_in_passage(text: str, reference_terms: list[str]) -> tuple[str, list[dict[str, Any]]]:
    """A window of text around the reference, and the words found in that window."""
    position = -1
    folded = text.casefold()
    for term in reference_terms:
        position = folded.find(term)
        if position != -1:
            break
    if position == -1:
        window = text[: _WINDOW * 2]
    else:
        window = text[max(0, position - _WINDOW) : position + _WINDOW]
    words = [
        {"word": word, "cautionary": cautionary}
        for word, pattern, cautionary in TREATMENT_WORDS
        if re.search(pattern, window, re.IGNORECASE)
    ]
    return " ".join(window.split()), words


def _search_terms(reference: CaseReference, held: HeldJudgment | None) -> list[str]:
    terms: list[str] = []
    if reference.citation:
        terms.append(reference.citation.casefold())
    tokens = sorted(party_tokens(reference.first or ""), key=len, reverse=True)
    if not tokens and held and held.parties:
        tokens = sorted(party_tokens(held.parties[0]), key=len, reverse=True)
    terms.extend(tokens[:2])
    return terms


async def _citing_passages(
    index: JudgmentIndex,
    judgments: dict[str, HeldJudgment],
    reference: CaseReference,
    held: HeldJudgment | None,
    *,
    per_judgment: int = 2,
    max_judgments: int = 12,
) -> list[dict[str, Any]]:
    parties: tuple[str, str] | None = None
    if reference.first and reference.second:
        parties = (reference.first, reference.second)
    elif held is not None:
        parties = held.parties
    citations = {normalise_citation(reference.citation)} if reference.citation else set()
    if held is not None:
        citations |= held.self_citations()
    matches: list[tuple[HeldJudgment, list[Any]]] = []
    for candidate in judgments.values():
        if held is not None and candidate.document_id == held.document_id:
            continue
        chunks = [
            chunk for chunk in candidate.chunks
            if any(edge_matches(edge, parties=parties, citations=citations) for edge in chunk.cited_cases)
        ]
        if chunks:
            matches.append((candidate, chunks[:per_judgment]))
    matches.sort(key=lambda pair: (pair[0].decision_year or 0), reverse=True)
    shown = matches[:max_judgments]
    payloads = await index.fetch_chunks(chunk.point_id for _, chunks in shown for chunk in chunks)
    terms = _search_terms(reference, held)
    rows: list[dict[str, Any]] = []
    for candidate, chunks in shown:
        passages = []
        for chunk in chunks:
            payload = payloads.get(chunk.point_id)
            if payload is None:
                continue
            window, words = _treatment_in_passage(str(payload.get("text") or ""), terms)
            passages.append(
                {"window": window, "words_near_reference": words, "source": source_from_payload(payload, score=None)}
            )
        rows.append({**candidate.summary(), "passages": passages})
    return rows


def _provision_rows(keys: set[str]) -> list[dict[str, Any]]:
    rows = []
    for key in sorted(keys):
        act, _, section = key.partition(":")
        code = _CODE_BY_KEY.get(act.casefold())
        if code is None or not section:
            continue
        check = _check_one(code, section, f"{code} s.{section}")
        rows.append(_check_row(check))
    # The concerns first: repealed law must not be buried in a long list.
    return sorted(rows, key=lambda row: not row["needs_attention"])


def _check_row(check: Any) -> dict[str, Any]:
    return {
        "citation": check.citation,
        "code": check.code,
        "section": check.section,
        "finding": check.finding.value,
        "successors": list(check.successors),
        "advice": check.advice,
        "needs_attention": check.needs_attention,
    }


async def _treatment_of_provision(index: JudgmentIndex, judgments: dict[str, HeldJudgment], key: str) -> list[dict[str, Any]]:
    citing = []
    for held in judgments.values():
        pages = sorted({chunk.page_start for chunk in held.chunks if key in chunk.cited_provisions})
        if pages:
            citing.append({**held.summary(), "pages": pages[:12]})
    citing.sort(key=lambda row: row["decision_year"] or 0, reverse=True)
    return citing


async def check_treatment(*, index: JudgmentIndex, reference_text: str) -> dict[str, Any]:
    """What the held material shows about one judgment or provision.

    Never concludes whether an authority stands. There is no field for that,
    so no caller can render one.
    """
    judgments = await index.judgments()
    coverage = coverage_of(judgments.values())
    parsed = parse_case_references(reference_text)
    provisions = list(extract_references(reference_text).provisions)
    base: dict[str, Any] = {
        "label": TREATMENT_LABEL,
        "limits": list(TREATMENT_LIMITS),
        "coverage": coverage_statement(coverage),
        "reference": reference_text.strip(),
        "recognised": bool(parsed or provisions),
        "held": [],
        "cited_by": [],
        "cites": [],
        "provisions": [],
        "cited_by_provision": [],
    }
    if provisions and not parsed:
        base["provisions"] = _provision_rows(set(provisions))
        cited: list[dict[str, Any]] = []
        for key in provisions[:4]:
            for row in await _treatment_of_provision(index, judgments, key):
                cited.append({**row, "provision": key})
        base["cited_by_provision"] = cited
        return base
    if not parsed:
        # "Lalita Kumari" alone is a reasonable thing to type.
        names = reference_text.strip()
        if party_tokens(names):
            parsed = [CaseReference(raw=names, first=names, second="", context=names)]
            base["recognised"] = True
        else:
            return base
    reference = parsed[0]
    if reference.first and not reference.second:
        tokens = party_tokens(reference.first)
        candidates = [
            {**held.summary(), "match_basis": "party_names", "confidence": "possible",
             "match_note": "Matched on a word in the title. Confirm it is the same judgment."}
            for held in judgments.values()
            if tokens and tokens <= party_tokens(held.title)
        ]
    else:
        candidates = find_held(reference, judgments)
    base["held"] = candidates
    held = judgments.get(candidates[0]["document_id"]) if candidates else None
    base["cited_by"] = await _citing_passages(index, judgments, reference, held)
    if held is not None:
        base["cites"] = sorted(
            {edge for chunk in held.chunks for edge in chunk.cited_cases}
        )[:40]
        base["provisions"] = _provision_rows(
            {edge for chunk in held.chunks for edge in chunk.cited_provisions}
        )
    return base


_STOP = frozenset(
    "the a an of to in on at by for from with that this it is was were be been are as and or not no "
    "which who whom whose has have had but if then than there their they he she his her its".split()
)


def _terms(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z]{3,}", text.casefold()) if word not in _STOP}


def best_passages(chunks: list[dict[str, Any]], context: str, *, limit: int = 2) -> list[dict[str, Any]]:
    """The passages of one judgment sharing the most words with the context.

    Term overlap rather than the vector index, since the question here is "where
    in this one judgment", and an unrelated first page is the only other choice.
    """
    wanted = _terms(context)
    scored = sorted(
        ((len(wanted & _terms(str(chunk.get("text") or ""))), position, chunk) for position, chunk in enumerate(chunks)),
        key=lambda item: (-item[0], item[1]),
    )
    return [chunk for score, _, chunk in scored[:limit] if score > 0]


async def check_opponent_authorities(*, index: JudgmentIndex, text: str) -> dict[str, Any]:
    """Every authority in a filing: held or not, what it says, what has been repealed."""
    coverage = None
    judgments: dict[str, HeldJudgment] = {}
    try:
        judgments = await index.judgments()
        coverage = coverage_of(judgments.values())
    except CorpusUnavailable:
        pass
    rows: list[dict[str, Any]] = []
    for reference in parse_case_references(text):
        candidates = find_held(reference, judgments)
        passages: list[dict[str, Any]] = []
        if candidates:
            chunks = await index.document_chunks(candidates[0]["document_id"])
            passages = [source_from_payload(chunk, score=None) for chunk in best_passages(chunks, reference.context)]
        citing_count = 0
        held = judgments.get(candidates[0]["document_id"]) if candidates else None
        parties = (reference.first, reference.second) if reference.first and reference.second else None
        citations = {normalise_citation(reference.citation)} if reference.citation else set()
        for candidate in judgments.values():
            if held is not None and candidate.document_id == held.document_id:
                continue
            if any(
                edge_matches(edge, parties=parties, citations=citations)
                for chunk in candidate.chunks
                for edge in chunk.cited_cases
            ):
                citing_count += 1
        rows.append(
            {
                "reference": reference.raw,
                "proposition_context": reference.context,
                "held": bool(candidates),
                "candidates": candidates,
                "passages": passages,
                "cited_in_held_judgments": citing_count,
                "not_found_note": (
                    ""
                    if candidates
                    else "Not among the judgments held. This says nothing about whether it exists, or whether it says what is claimed."
                ),
            }
        )
    checks = check_authorities(text)
    return {
        "coverage": coverage_statement(coverage, what="Compared against"),
        "limits": list(OPPONENT_LIMITS),
        "cases": rows,
        "provisions": sorted((_check_row(check) for check in checks), key=lambda row: not row["needs_attention"]),
        "repealed_provisions": sum(
            1 for check in checks if check.code in {"IPC", "CrPC", "IEA"}
        ),
        "needs_attention": sum(1 for check in checks if check.needs_attention),
    }


def judgment_catalogue(judgments: dict[str, HeldJudgment]) -> list[dict[str, Any]]:
    return sorted(
        (held.summary() for held in judgments.values()),
        key=lambda row: (row["decision_year"] or 0, row["title"]),
        reverse=True,
    )


__all__ = [
    "best_passages",
    "check_opponent_authorities",
    "check_treatment",
    "holding_sentences",
    "judgment_catalogue",
    "search_precedents",
]
