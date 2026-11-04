"""Check the provisions a draft cites, against the codes now in force.

The advocate's version of the currency problem. A petition drafted from a
2019 precedent, or from a form last revised in 2022, cites the CrPC and the
IPC throughout. Most of those provisions were renumbered on 1 July 2024,
some were substantively changed, and a few were not re-enacted at all --
and none of that is visible in the draft.

Deterministic end to end: the citations are extracted by the same parser
the ingestion pipeline uses, and resolved through the official NCRB
concordance. No model reads the draft, which matters because the failure
mode of a model here is to confidently renumber a provision that was
actually dropped.

Four findings, and the third is the one this exists for:

* still current -- the provision belongs to a code in force
* renumbered -- it moved, and the successor is named
* elements changed -- it moved AND the provision is not the same one, so
  citing the successor as though it were a renumbering gets the ingredients
  of the offence wrong
* not re-enacted -- there is no successor. Sedition is the example: a draft
  citing IPC s.124A is not fixed by writing BNS s.152 instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.ingestion.citations import extract_references
from app.services.section_mapping import REPLACED_BY, map_sections

__all__ = ["AuthorityFinding", "CitationCheck", "check_authorities"]

# Every act the citation extractor can name, not only the six the
# concordance covers. Dropping the others silently was the original bug: a
# petition citing POCSO s.4 or Article 21 produced no row at all, which is
# indistinguishable from a row saying it was checked and is fine. Anything
# outside the concordance is reported as NOT_CHECKED, by name.
_CODE_BY_KEY = {
    "ipc": "IPC",
    "crpc": "CrPC",
    "evidence": "IEA",
    "bns": "BNS",
    "bnss": "BNSS",
    "bsa": "BSA",
    "constitution": "Constitution",
    "pocso": "POCSO",
    "ndps": "NDPS Act",
    "cpc": "CPC",
    "it": "IT Act",
    "ni": "Negotiable Instruments Act",
    "juvenile_justice": "Juvenile Justice Act",
    "domestic_violence": "Domestic Violence Act",
    "prisons": "Prisons Act",
    "rti": "RTI Act",
}
_IN_FORCE_CODES = {"BNS", "BNSS", "BSA"}
_CONCORDANCE_CODES = {"IPC", "CrPC", "IEA", "BNS", "BNSS", "BSA"}
_NO_ACT_NAMED = "No Act named"


class AuthorityFinding(StrEnum):
    STILL_CURRENT = "still_current"
    RENUMBERED = "renumbered"
    ELEMENTS_CHANGED = "elements_changed"
    NOT_RE_ENACTED = "not_re_enacted"
    NO_MAPPING_KNOWN = "no_mapping_known"
    # Constitution articles, State legislation, anything the concordance does
    # not cover. Reported as unchecked rather than as fine.
    NOT_CHECKED = "not_checked"


@dataclass(frozen=True)
class CitationCheck:
    citation: str
    code: str
    section: str
    finding: AuthorityFinding
    successors: tuple[str, ...] = ()
    advice: str = ""

    @property
    def needs_attention(self) -> bool:
        """Anything a drafter must act on before filing.

        STILL_CURRENT and NOT_CHECKED are excluded, and NOT_CHECKED is
        excluded deliberately: it means nobody verified it, which is a
        prompt to look rather than a defect to fix, and folding it in here
        would bury the four findings that are.
        """
        return self.finding in {
            AuthorityFinding.RENUMBERED,
            AuthorityFinding.ELEMENTS_CHANGED,
            AuthorityFinding.NOT_RE_ENACTED,
            AuthorityFinding.NO_MAPPING_KNOWN,
        }


def _check_one(code: str, section: str, citation: str) -> CitationCheck:
    if code in _IN_FORCE_CODES:
        if not map_sections(code, section):
            return CitationCheck(
                citation=citation,
                code=code,
                section=section,
                finding=AuthorityFinding.NOT_CHECKED,
                advice=(
                    f"{code} is in force, but the official concordance has no entry "
                    f"for s.{section}. It may be a new provision or a wrong number, "
                    "so confirm it against the Act."
                ),
            )
        return CitationCheck(
            citation=citation,
            code=code,
            section=section,
            finding=AuthorityFinding.STILL_CURRENT,
            advice=f"{code} is in force; no renumbering applies.",
        )

    successor_code = REPLACED_BY.get(code)
    if successor_code is None:
        return CitationCheck(
            citation=citation,
            code=code,
            section=section,
            finding=AuthorityFinding.NOT_CHECKED,
            advice=(
                f"{code} is outside the 2023 criminal-law concordance, so its "
                "currency has not been verified here. Listed so that it is "
                "visibly unchecked rather than silently omitted."
            ),
        )

    mappings = map_sections(code, section)
    if not mappings:
        return CitationCheck(
            citation=citation,
            code=code,
            section=section,
            finding=AuthorityFinding.NO_MAPPING_KNOWN,
            advice=(
                f"{code} was repealed on 1 July 2024, and the official "
                f"concordance lists no counterpart for s.{section}. Confirm the "
                "provision number before relying on it."
            ),
        )

    if all(not m.has_successor for m in mappings):
        return CitationCheck(
            citation=citation,
            code=code,
            section=section,
            finding=AuthorityFinding.NOT_RE_ENACTED,
            advice=(
                f"{code} s.{section} was NOT carried forward into the "
                f"{successor_code}. There is no renumbered equivalent, so this "
                "citation cannot be corrected by substituting a new section "
                "number -- the provision no longer exists."
            ),
        )

    successors = tuple(
        f"{m.to_code} s.{m.to_section}" for m in mappings if m.has_successor
    )
    changed = any(m.ingredients_changed for m in mappings if m.has_successor)
    return CitationCheck(
        citation=citation,
        code=code,
        section=section,
        finding=(
            AuthorityFinding.ELEMENTS_CHANGED if changed else AuthorityFinding.RENUMBERED
        ),
        successors=successors,
        advice=(
            f"Now {', '.join(successors)}."
            + (
                " The official table marks this as changed, not a pure "
                "renumbering: check the elements before treating the two as "
                "equivalent."
                if changed
                else ""
            )
        ),
    )


_SECTION = r"\d{1,4}[A-Za-z]{0,2}(?:\(\d+\))*"
_SECTION_LIST = rf"{_SECTION}(?:\s*(?:,|/|&|\band\b|\br/w\b|\bread\s+with\b)\s*{_SECTION})*"
_CODE_NAMES = (
    r"(?P<code>indian\s+penal\s+code|i\.?p\.?c\.?|code\s+of\s+criminal\s+procedure|"
    r"cr\.?\s?p\.?\s?c\.?|indian\s+evidence\s+act|evidence\s+act|i\.?e\.?a\.?|"
    r"bharatiya\s+nyaya\s+sanhita|bharatiya\s+nagarik\s+suraksha\s+sanhita|"
    r"bharatiya\s+sakshya\s+adhiniyam|bnss|bns|bsa)"
)
# "Sections 302 and 34 IPC", "u/s 420, 468, 471 IPC", "section 438 of the CrPC".
_NUMBERS_THEN_CODE = re.compile(
    rf"\b(?:u/s|under\s+sections?|sections?|secs?\.?|ss?\.)\s*(?P<numbers>{_SECTION_LIST})"
    rf"\s*,?\s*(?:(?:of|under)\s+(?:the\s+)?)?{_CODE_NAMES}(?![a-z])",
    re.I,
)
# "IPC 302", "IPC s.302", "under the CrPC, section 154".
_CODE_THEN_NUMBERS = re.compile(
    rf"(?<![a-z]){_CODE_NAMES}\s*,?\s*(?:u/s|sections?|secs?\.?|ss?\.)?\s*(?P<numbers>{_SECTION_LIST})",
    re.I,
)
_YEAR = re.compile(r"(?:18|19|20)\d\d")


def _concordance_code(name: str) -> str | None:
    folded = re.sub(r"[\s.]+", "", name).casefold()
    if "penal" in folded or folded == "ipc":
        return "IPC"
    if "criminalprocedure" in folded or folded == "crpc":
        return "CrPC"
    if "evidenceact" in folded or folded == "iea":
        return "IEA"
    if "nyaya" in folded or folded == "bns":
        return "BNS"
    if "nagarik" in folded or folded == "bnss":
        return "BNSS"
    if "sakshya" in folded or folded == "bsa":
        return "BSA"
    return None


def _concordance_citations(draft: str) -> list[tuple[int, str, str]]:
    """Position, code and section of each citation to the six concordance codes.

    Stricter than the ingestion parser, which reads one number per reference and
    borrows the nearest Act within 120 characters. That is right for building a
    graph, where a missing edge is harmless. Here a missing row reads as "checked
    and fine": "Sections 302 and 34 IPC" checked only 302, "IPC 302" found nothing,
    and "Section 3 of the SC/ST Act read with section 498A IPC" reported IPC s.3.
    """
    found: list[tuple[int, str, str]] = []
    for pattern in (_NUMBERS_THEN_CODE, _CODE_THEN_NUMBERS):
        for match in pattern.finditer(draft):
            code = _concordance_code(match.group("code"))
            if code is None:
                continue
            for number in re.findall(_SECTION, match.group("numbers")):
                section = re.sub(r"\(.*", "", number).upper()
                if _YEAR.fullmatch(section):
                    continue
                found.append((match.start(), code, section))
    return sorted(found, key=lambda item: item[0])


def check_authorities(draft: str, *, max_citations: int = 60) -> list[CitationCheck]:
    """Every provision the draft cites, in the order it cites them.

    Duplicates collapse: a provision cited eight times is one finding, not
    eight, or a long petition drowns its own warnings. A section with no Act named
    is listed as unchecked, because leaving it out reads as having checked it.
    """
    draft = draft or ""
    references = extract_references(draft, max_references=max_citations)
    seen: set[tuple[str, str]] = set()
    results: list[CitationCheck] = []

    def add(code: str, section: str) -> None:
        if (code, section) not in seen:
            seen.add((code, section))
            results.append(_check_one(code, section, f"{code} s.{section}"))

    for _, code, section in _concordance_citations(draft):
        add(code, section)
    for reference in references.provisions:
        key, _, section = str(reference).partition(":")
        code = _CODE_BY_KEY.get(key.casefold())
        if code is None or not section or code in _CONCORDANCE_CODES:
            continue
        add(code, section)
    for number in references.unresolved_sections:
        section = str(number).upper()
        if not any(section == known for _, known in seen):
            add(_NO_ACT_NAMED, section)
    return results
