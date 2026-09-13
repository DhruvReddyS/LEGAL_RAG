"""Reach the provision in force by following what the corpus already cites.

A citizen asks "how is an FIR registered?". BNSS s.173 answers it and
contains none of those words -- it says "information relating to the
commission of a cognizable offence". Measured: the section does not appear
in the top 100 for that question, while its own text retrieves it at rank 1.
So the index is sound and the gap is between how statutes are drafted and
how people ask.

What *does* rank for that question is judgments about FIR registration, and
those judgments cite CrPC s.154 -- the repealed provision, because they
predate the 2023 Sanhitas. The official NCRB concordance says CrPC s.154 is
now BNSS s.173.

So the corpus can reach the governing provision on its own: read what the
retrieved passages rely on, follow those citations forward through the
concordance, and fetch the result. It is how a lawyer works -- read the
commentary, follow it to the statute -- and it needs no model, no
hand-written statutory phrasing, and no re-indexing.

Measured over five questions whose governing provision retrieval could not
reach at all:

    how is an FIR registered          -> BNSS s.173, cited 9 times
    anticipatory bail grounds         -> BNSS s.482, cited 6 times
    arrest without a warrant          -> BNSS s.35,  cited 4 times
    which law governs theft           -> BNS s.303, reached
    what is default bail              -> not reached (see below)

Default bail is the honest miss: the passages cite CrPC ss.437 and 437A,
which map to the BNSS bail sections rather than to s.187, whose proviso is
what actually creates the entitlement. Following citations reaches what the
sources rely on, which is not always what the question needs.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from app.services.section_mapping import map_sections

__all__ = [
    "FollowedProvision",
    "implementation_provisions_for_query",
    "provisions_worth_following",
]

# How the citation extractor keys the repealed codes, and the concordance's
# name for each. Only the three replaced codes are followed: a citation to a
# code still in force needs no forwarding.
_REPEALED_CODE_KEYS = {"crpc": "CrPC", "ipc": "IPC", "evidence": "IEA"}

# Bounded deliberately. A judgment cites many provisions in passing, and
# fetching every successor would swamp the result set with material the
# question never asked about.
MAX_FOLLOWED = 3

# One citation is an aside. This asks for corroboration across the retrieved
# passages before treating a provision as the one they rest on.
MIN_CITATIONS = 2


@dataclass(frozen=True)
class _Concept:
    """One way of asking about a provision, as groups of interchangeable terms.

    Every group in `all_of` must be present and no group in `none_of` may be.
    A term with a space is a phrase matched on the normalised question; any
    other term is a word prefix, so "arrest" covers "arrested" and "arresting".

    These describe what a question is about, not how the golden set happens to
    word it. The first version matched the evaluation questions almost word for
    word -- "now governs" plus "arrest" plus "without a warrant" -- and reached
    one of ten reworded questions. A table keyed to the test measures the
    table, not retrieval.
    """

    code: str
    section: str
    via: str
    all_of: tuple[tuple[str, ...], ...]
    none_of: tuple[tuple[str, ...], ...] = ()


_CURRENCY_CUES = (
    "replac", "repeal", "still", "now", "new", "current", "govern", "appl",
    "in force", "after", "which law", "what law", "which act", "valid",
)

_CONCEPTS: tuple[_Concept, ...] = (
    # BNSS s.187's proviso creates the entitlement, and the passages that rank
    # for bail questions cite CrPC ss.437/437A instead, so citation forwarding
    # never reaches it. Asked either by name or by its trigger: the charge
    # sheet not filed within the statutory period.
    _Concept(
        "BNSS", "187", "default-bail implementation",
        all_of=(("bail",), ("default", "statutory", "compulsive", "compulsory", "indefeasible")),
        none_of=(("anticipat", "cancel"),),
    ),
    _Concept(
        "BNSS", "187", "default-bail implementation",
        all_of=(
            ("charge sheet", "chargesheet", "final report", "investigation"),
            ("day", "deadline", "time limit", "in time", "not filed", "without filing",
             "not complet", "incomplete", "delay", "miss"),
            ("bail", "release", "get out", "jail", "custody", "entitled"),
        ),
        none_of=(("anticipat", "cancel"),),
    ),
    _Concept(
        "BNS", "303", "theft implementation",
        all_of=(
            ("theft", "steal", "stole", "thief", "thiev"),
            ("law", "code", "section", "defin", "punish", "offen", "crime", "ipc",
             "bns", "sanhita", "cover", "say") + _CURRENCY_CUES,
        ),
        # Offences built on theft have their own sections; the definition
        # would take a display slot from the provision actually asked about.
        none_of=(("receiv", "robber", "dacoit", "extort", "snatch"),),
    ),
    # A constitutional right (Article 22) implemented by a procedural section:
    # no repeal mapping connects them, so nothing cites its way there.
    _Concept(
        "BNSS", "47", "arrest-right implementation",
        all_of=(
            ("arrest", "detain", "picked up"),
            ("why", "reason", "ground", "cause"),
            ("tell", "told", "inform", "communicat", "explain", "know", "said", "given"),
        ),
    ),
    _Concept(
        "BNSS", "35", "warrantless-arrest implementation",
        all_of=(
            ("arrest",),
            ("without warrant", "without a warrant", "warrantless", "warrant less", "no warrant"),
        ),
    ),
    # Asking which evidence law applies is answered by the Act itself, whose
    # first section brings it into force in place of the 1872 Act.
    _Concept(
        "BSA", "1", "evidence-law currency",
        all_of=(
            ("evidence act", "evidence law", "law of evidence", "laws of evidence",
             "indian evidence", "sakshya"),
            _CURRENCY_CUES,
        ),
    ),
    _Concept(
        "BSA", "1", "evidence-law currency",
        all_of=(("evidence",), ("which law", "what law", "which act", "what act")),
    ),
)

# Naming a repealed section in the question is the most direct signal there
# is, and the official concordance already knows where each one went -- so
# every repealed section is bridged, not only the ones someone measured.
_OLD_CODE_NAMES = (
    (re.compile(r"\b(?:i\.?\s?p\.?\s?c|indian\s+penal\s+code|penal\s+code)\b", re.I), "IPC"),
    (re.compile(r"\b(?:cr\.?\s?p\.?\s?c|code\s+of\s+criminal\s+procedure|criminal\s+procedure\s+code)\b", re.I), "CrPC"),
    (re.compile(r"\b(?:i\.?\s?e\.?\s?a|(?:indian\s+)?evidence\s+act)\b", re.I), "IEA"),
)
_SECTION_NUMBER = re.compile(
    r"(?:\b(?:section|sec\.?|s\.|u/s)\s*)?\b(\d{1,3}[A-Z]?)\b(?:\s*\(\d+\))?", re.I
)
# A number this far from its code name is not a reference to that code.
_REFERENCE_WINDOW = 18


def _normalise(query: str) -> str:
    return " ".join(re.sub(r"[-_/]", " ", str(query or "").lower()).split())


def _present(term: str, text: str, words: tuple[str, ...]) -> bool:
    if " " in term:
        return term in text
    return any(word.startswith(term) for word in words)


def _concordance_provisions(query: str) -> list["FollowedProvision"]:
    text = str(query or "")
    codes = [(m.start(), m.end(), code) for pattern, code in _OLD_CODE_NAMES for m in pattern.finditer(text)]
    if not codes:
        return []
    found: list[FollowedProvision] = []
    for match in _SECTION_NUMBER.finditer(text):
        number = match.group(1)
        nearest = min(
            codes,
            key=lambda span: min(abs(match.start() - span[1]), abs(span[0] - match.end())),
        )
        gap = min(abs(match.start() - nearest[1]), abs(nearest[0] - match.end()))
        if gap > _REFERENCE_WINDOW:
            continue
        for mapping in map_sections(nearest[2], number):
            if not mapping.has_successor or not mapping.to_section:
                continue
            section = str(mapping.to_section).split("(")[0]
            found.append(
                FollowedProvision(
                    code=mapping.to_code, section=section, citations=0,
                    via=f"concordance: {nearest[2]} s.{number}",
                )
            )
    return found


@dataclass(frozen=True)
class FollowedProvision:
    code: str
    section: str
    citations: int
    via: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.code, self.section)


def implementation_provisions_for_query(query: str) -> list[FollowedProvision]:
    """The provisions a question itself points at, before any retrieval.

    Citation forwarding cannot recover a provision when the retrieved passages
    do not cite its predecessor, or when the relation is a right implemented by
    a procedural section rather than a repeal. Two sources close that gap: a
    repealed section named in the question, routed through the official
    concordance, and a small set of concepts for measured misses. Both only
    trigger a lookup; the fetched text must still pass the normal relevance and
    verification gates.
    """
    text = _normalise(query)
    words = tuple(re.findall(r"[a-z0-9]+", text))
    found = _concordance_provisions(query)
    for concept in _CONCEPTS:
        if all(any(_present(term, text, words) for term in group) for group in concept.all_of) and not any(
            any(_present(term, text, words) for term in group) for group in concept.none_of
        ):
            found.append(
                FollowedProvision(code=concept.code, section=concept.section, citations=0, via=concept.via)
            )
    unique: dict[tuple[str, str], FollowedProvision] = {}
    for provision in found:
        unique.setdefault(provision.key, provision)
    return list(unique.values())


def provisions_worth_following(hits: list) -> list[FollowedProvision]:
    """The in-force provisions the retrieved passages rely on, most-cited first.

    Deterministic: the same hits give the same list, ordered by citation
    weight and then by provision, so a measurement means something.
    """
    weight: Counter[tuple[str, str]] = Counter()
    via: dict[tuple[str, str], str] = {}

    for hit in hits:
        payload = getattr(hit, "payload", None) or {}
        for reference in payload.get("cited_provisions") or []:
            key, _, section = str(reference).lower().partition(":")
            code = _REPEALED_CODE_KEYS.get(key)
            if code is None or not section:
                continue
            # One citation is one vote, however many rows the concordance
            # holds for it. CrPC s.154 has three -- BNSS 173, 173(1) and
            # 173(3) -- and counting rows made a single passing mention
            # outvote a provision three passages agreed on.
            successors = {
                (mapping.to_code, str(mapping.to_section).split("(")[0])
                for mapping in map_sections(code, section)
                if mapping.has_successor
            }
            for target in successors:
                weight[target] += 1
                via.setdefault(target, f"{code} s.{section}")

    ranked = sorted(
        (item for item in weight.items() if item[1] >= MIN_CITATIONS),
        key=lambda item: (-item[1], item[0][0], item[0][1]),
    )
    return [
        FollowedProvision(code=code, section=section, citations=count, via=via[(code, section)])
        for (code, section), count in ranked[:MAX_FOLLOWED]
    ]
