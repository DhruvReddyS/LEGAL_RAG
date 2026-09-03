"""Extract legal cross-references from chunk text.

Legal writing cites by convention, and those conventions are machine-readable:
"Section 154 of the Code of Criminal Procedure, 1973", "Article 21", "(2014) 2
SCC 1". Roughly half the corpus carries at least one such reference, which is
about 52,500 edges — enough to answer "which judgments construe this provision"
without asking a model anything.

Extraction is deterministic on purpose. An LLM pass over 25,517 chunks costs
days of GPU time on this hardware and has to be repeated whenever chunking
changes; more importantly it cannot run on a citizen's uploaded document, which
is never pre-indexed. The same regex runs on an upload in milliseconds.

The output is a retrieval hint, never an authority claim. Indian citation
formats vary, OCR damages them, and a bare "section 14" is ambiguous. Precision
here is good, not perfect, and nothing downstream may treat an edge as proof.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# Canonical keys for the Acts this corpus actually contains. A reference
# resolves to one of these or stays unresolved; inventing a key for every Act
# ever mentioned would produce a graph mostly made of dangling nodes.
ACT_KEYS: dict[str, tuple[str, ...]] = {
    "constitution": ("constitution of india", "the constitution"),
    "crpc": (
        "code of criminal procedure",
        "criminal procedure code",
        "cr.p.c",
        "crpc",
        "cr p c",
    ),
    "ipc": ("indian penal code", "penal code", "i.p.c", "ipc"),
    "bns": ("bharatiya nyaya sanhita", "bns"),
    "bnss": ("bharatiya nagarik suraksha sanhita", "bnss"),
    "bsa": ("bharatiya sakshya adhiniyam", "bsa"),
    "evidence": ("indian evidence act", "evidence act"),
    "pocso": (
        "protection of children from sexual offences",
        "pocso",
    ),
    "ndps": ("narcotic drugs and psychotropic substances", "ndps"),
    "cpc": ("code of civil procedure", "civil procedure code", "c.p.c"),
    "it": ("information technology act",),
    "ni": ("negotiable instruments act",),
    "juvenile_justice": ("juvenile justice",),
    "domestic_violence": ("protection of women from domestic violence",),
    "prisons": ("prisons act",),
    "rti": ("right to information",),
}

# Longest first, so "code of criminal procedure" wins over a bare "crpc" that
# happens to appear inside it.
_ACT_ALIASES: list[tuple[str, str]] = sorted(
    ((alias, key) for key, aliases in ACT_KEYS.items() for alias in aliases),
    key=lambda pair: len(pair[0]),
    reverse=True,
)

# "Section 154", "S. 154", "Sec. 154", "u/s 154", "Sections 154 and 156"
_SECTION_RE = re.compile(
    r"\b(?:u/s|under\s+section|sections?|secs?\.|ss\.|s\.)\s*"
    r"(?P<number>\d{1,4}[A-Z]{0,2})\b",
    re.IGNORECASE,
)

# "Article 14", "Art. 21", "Articles 14 and 21". The abbreviation must carry
# its full stop: "art 32" without one is more often the ordinary word than a
# constitutional reference, and a false edge costs more than a missed one.
_ARTICLE_RE = re.compile(
    r"\b(?:articles?|arts?\.)\s*(?P<number>\d{1,3}[A-Z]{0,2})\b",
    re.IGNORECASE,
)

# Reported citations. Kept narrow: a loose pattern turns page numbers into
# citations, and a graph full of false edges is worse than a sparse one.
_REPORTED_RE = re.compile(
    r"\(\s*(?P<year1>(?:19|20)\d{2})\s*\)\s*(?P<vol>\d{1,3})\s*"
    r"(?P<reporter1>SCC|SCR|SCALE|AIR)\s*(?P<page>\d{1,5})"
    r"|(?P<reporter2>AIR)\s*(?P<year2>(?:19|20)\d{2})\s*(?P<court>SC|SCC|Del|Bom|Mad|Cal|All|Ker|Kar)\s*(?P<page2>\d{1,5})"
    r"|(?P<year3>(?:19|20)\d{2})\s*(?P<reporter3>INSC)\s*(?P<page3>\d{1,5})",
    re.IGNORECASE,
)

# "Lalita Kumari v. Govt of U.P." — capitalised party names around a "v."
_CASE_NAME_RE = re.compile(
    r"\b(?P<first>[A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+){0,4})"
    r"\s+v[s]?\.?\s+"
    r"(?P<second>[A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+){0,4})",
)

# Words that look like a party name but are not one. "Anr." and "Ors." are
# the tail of a party list — "Ram Kumar & Ors. v. State" — so a match starting
# there has clipped the actual first party and produces "Ors. v. State", an
# edge that points at every case in the corpus.
_CASE_NAME_STOPWORDS = frozenset(
    {
        "the", "in", "see", "and", "of", "at", "para", "supra", "hon",
        "ors", "anr", "others", "another", "etc", "vs", "v",
    }
)

# How far back to look for the Act a section belongs to. A section number and
# its Act are normally within a clause of each other; searching further picks up
# whichever Act was last mentioned in the paragraph, which is usually wrong.
_ACT_CONTEXT_CHARACTERS = 120


@dataclass(frozen=True)
class ExtractedReferences:
    """References found in one chunk.

    `provisions` are `act_key:number` strings, e.g. "crpc:154". `cases` are
    normalised reported citations or party-name pairs. `unresolved_sections`
    are section numbers whose Act could not be determined; they are kept
    separately rather than guessed at, because a wrong Act is a worse edge than
    no edge.
    """

    provisions: tuple[str, ...] = ()
    cases: tuple[str, ...] = ()
    unresolved_sections: tuple[str, ...] = field(default=())

    def as_payload(self) -> dict[str, list[str]]:
        return {
            "cited_provisions": list(self.provisions),
            "cited_cases": list(self.cases),
        }


def resolve_act(text: str) -> str | None:
    """Return the canonical key for the first Act named in `text`."""
    folded = text.casefold()
    best: tuple[int, str] | None = None
    for alias, key in _ACT_ALIASES:
        position = folded.find(alias)
        if position != -1 and (best is None or position < best[0]):
            best = (position, key)
    return best[1] if best else None


def _act_for_section(text: str, match: re.Match[str], self_act: str | None) -> str | None:
    """Which Act a section reference belongs to.

    Looks just after the reference first — "section 154 of the Code of Criminal
    Procedure" — then just before it, which covers "under the CrPC, section
    154". Falling back to the containing document's own Act is deliberate and
    correct: an unqualified section reference inside the CrPC means the CrPC.
    """
    tail = text[match.end() : match.end() + _ACT_CONTEXT_CHARACTERS]
    resolved = resolve_act(tail)
    if resolved:
        return resolved
    head = text[max(0, match.start() - _ACT_CONTEXT_CHARACTERS) : match.start()]
    resolved = resolve_act(head)
    if resolved:
        return resolved
    return self_act


def _normalise_case_name(first: str, second: str) -> str | None:
    def leading_word(value: str) -> str:
        return value.split()[0].casefold().strip(".,&")

    if leading_word(first) in _CASE_NAME_STOPWORDS:
        return None
    if leading_word(second) in _CASE_NAME_STOPWORDS:
        return None
    # A single-token party on both sides is almost always a sentence fragment
    # rather than a case; real citations name at least one party properly.
    if len(first.split()) == 1 and len(second.split()) == 1:
        return None
    return f"{' '.join(first.split())} v. {' '.join(second.split())}"


def _reported_citation(match: re.Match[str]) -> str | None:
    groups = match.groupdict()
    if groups.get("reporter1"):
        return (
            f"({groups['year1']}) {groups['vol']} "
            f"{groups['reporter1'].upper()} {groups['page']}"
        )
    if groups.get("reporter2"):
        return f"AIR {groups['year2']} {groups['court'].upper()} {groups['page2']}"
    if groups.get("reporter3"):
        return f"{groups['year3']} INSC {groups['page3']}"
    return None


def extract_references(
    text: str,
    *,
    self_act: str | None = None,
    max_references: int = 40,
) -> ExtractedReferences:
    """Find the legal cross-references in a passage.

    `self_act` is the canonical key of the document the passage came from, used
    to resolve unqualified section references. Pass the result of
    `resolve_act(document.act_name or document.title)`.

    `max_references` bounds a pathological chunk — a table of contents can list
    hundreds of section numbers, and those are furniture rather than citations.
    """
    if not text or not text.strip():
        return ExtractedReferences()

    provisions: list[str] = []
    unresolved: list[str] = []

    for match in _SECTION_RE.finditer(text):
        number = match.group("number").upper()
        act = _act_for_section(text, match, self_act)
        if act:
            provisions.append(f"{act}:{number}")
        else:
            unresolved.append(number)

    for match in _ARTICLE_RE.finditer(text):
        # An article number is a constitutional reference in this corpus;
        # no other indexed instrument is numbered by article.
        provisions.append(f"constitution:{match.group('number').upper()}")

    cases: list[str] = []
    for match in _REPORTED_RE.finditer(text):
        citation = _reported_citation(match)
        if citation:
            cases.append(citation)
    for match in _CASE_NAME_RE.finditer(text):
        name = _normalise_case_name(match.group("first"), match.group("second"))
        if name:
            cases.append(name)

    return ExtractedReferences(
        provisions=tuple(dict.fromkeys(provisions))[:max_references],
        cases=tuple(dict.fromkeys(cases))[:max_references],
        unresolved_sections=tuple(dict.fromkeys(unresolved))[:max_references],
    )
