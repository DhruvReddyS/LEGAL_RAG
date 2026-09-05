"""Two distinct things a reader needs to be told, and they are not the same.

Label A -- *this document is no longer in force*. It attaches to the repealed
authority itself: the Penal Code, the 1973 Code, the Evidence Act.

Label B -- *this document concerns a provision that has been repealed,
replaced or renumbered*. It attaches to material **about** those provisions: an
SOP written against CrPC s.154, a circular on IPC s.498A, a judgment
construing s.65B. Those documents are themselves operative, and marking them
"no longer in force" would be false in a way a police reader would spot
immediately.

The distinction was forced by a real case. "can you help me now with the FIR
procedure" cited *Amendment in Section 154 of the Code of Criminal Procedure*
with no marker at all, because the repeal rule matches a name that *begins*
with a repealed code and that document does not. Loosening the name match was
the wrong fix: it would have put "no longer in force" on guidance that still
binds. The right fix is a second label with its own meaning.

Label B needs two inputs that already exist: a document-type signal, from
`source_type`, and the citation extractor, which yields `crpc:154` style
references deterministically from the text.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.ingestion.citations import extract_references
from app.services.currency import CurrencyStatus, resolve_currency
from app.services.section_mapping import (
    REPLACED_BY,
    SectionMapping,
    map_section,
)


class RepealLabel(StrEnum):
    NONE = "none"
    NO_LONGER_IN_FORCE = "no_longer_in_force"
    CONCERNS_REPEALED_PROVISION = "concerns_repealed_provision"


# Document types that *are* the authority. Everything else is material about
# it: guidance, manuals, handbooks, reports and judgments remain operative even
# when the provision they discuss has been replaced.
_AUTHORITY_TYPES = frozenset({"ACT", "RULE", "NOTIFICATION", "ORDER"})

# The citation extractor's keys for the three repealed codes.
_REPEALED_CODE_KEYS = {"ipc": "IPC", "crpc": "CrPC", "evidence": "IEA"}

_MAX_MAPPINGS = 6


@dataclass(frozen=True)
class RepealNotice:
    label: RepealLabel
    replaced_by: str | None = None
    repealed_on: str | None = None
    # Populated for Label B: which cited provisions moved, and where to.
    mappings: tuple[SectionMapping, ...] = ()
    # Cited provisions of a repealed code for which no mapping is known. Named
    # rather than hidden: silence would read as "unchanged".
    unmapped_provisions: tuple[str, ...] = ()
    review_status: str = ""

    @property
    def has_ingredient_changes(self) -> bool:
        """Whether any mapped provision is more than a renumbering.

        The dangerous case. A reader who treats BNS s.152 as "IPC s.124A,
        renumbered" has the elements of the offence wrong.
        """
        return any(mapping.ingredients_changed for mapping in self.mappings)


def _is_the_authority_itself(payload: dict[str, Any]) -> bool:
    return str(payload.get("source_type") or "").upper() in _AUTHORITY_TYPES


def repeal_notice(payload: dict[str, Any]) -> RepealNotice:
    """Which label, if any, this passage needs.

    Label A wins where both could apply: a repealed Act that cites its own
    sections is still, first and foremost, no longer in force.
    """
    currency = resolve_currency(payload)

    if currency.status is CurrencyStatus.SUPERSEDED:
        return RepealNotice(
            label=RepealLabel.NO_LONGER_IN_FORCE,
            replaced_by=currency.superseded_by,
            repealed_on=currency.effective,
        )

    # Label B only applies to material about the law. An Act that is in force
    # and happens to mention another Act's section needs no notice.
    if _is_the_authority_itself(payload):
        return RepealNotice(label=RepealLabel.NONE)

    text = str(payload.get("text") or "")
    if not text.strip():
        return RepealNotice(label=RepealLabel.NONE)

    # Prefer the provisions ingestion already extracted; fall back to the text
    # so this works against an index built before that field existed.
    stored = payload.get("cited_provisions")
    provisions: tuple[str, ...]
    if stored:
        provisions = tuple(str(item) for item in stored)
    else:
        provisions = extract_references(text).provisions

    mappings: list[SectionMapping] = []
    unmapped: list[str] = []
    seen: set[str] = set()
    for reference in provisions:
        act_key, _, section = str(reference).partition(":")
        code = _REPEALED_CODE_KEYS.get(act_key.casefold())
        if code is None or not section or reference in seen:
            continue
        seen.add(reference)
        mapping = map_section(code, section)
        if mapping is not None:
            mappings.append(mapping)
        else:
            unmapped.append(f"{code} s.{section}")

    if not mappings and not unmapped:
        return RepealNotice(label=RepealLabel.NONE)

    replacement = None
    if mappings:
        replacement = REPLACED_BY.get(mappings[0].from_code)

    return RepealNotice(
        label=RepealLabel.CONCERNS_REPEALED_PROVISION,
        replaced_by=replacement,
        repealed_on="2024-07-01",
        mappings=tuple(mappings[:_MAX_MAPPINGS]),
        unmapped_provisions=tuple(unmapped[:_MAX_MAPPINGS]),
        review_status=mappings[0].review_status if mappings else "pending_legal_review",
    )
