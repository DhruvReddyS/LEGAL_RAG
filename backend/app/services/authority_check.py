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


def check_authorities(draft: str, *, max_citations: int = 60) -> list[CitationCheck]:
    """Every provision the draft cites, in the order it cites them.

    Duplicates collapse: a provision cited eight times is one finding, not
    eight, or a long petition drowns its own warnings.
    """
    references = extract_references(draft or "", max_references=max_citations)
    seen: set[tuple[str, str]] = set()
    results: list[CitationCheck] = []
    for reference in references.provisions:
        key, _, section = str(reference).partition(":")
        code = _CODE_BY_KEY.get(key.casefold())
        if code is None or not section:
            continue
        if (code, section) in seen:
            continue
        seen.add((code, section))
        results.append(_check_one(code, section, f"{code} s.{section}"))
    return results
