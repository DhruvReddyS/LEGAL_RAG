"""Bidirectional lookup between the repealed codes and their replacements.

The renumbering of the IPC, CrPC and Indian Evidence Act into the BNS, BNSS
and BSA is the highest-frequency currency question in Indian law right now,
and a police corpus is full of SOPs and circulars written against the old
numbers. A reader who lands on "section 154" needs to be told it is now BNSS
s.173, and a reader who lands on BNSS s.173 needs to be able to follow the
old case law back.

Deterministic by requirement: a table, not a prompt.

The table is built from the National Crime Records Bureau's published
correspondence tables by scripts/build_section_mapping.py. It is not
inferred and not model-authored, and the difference is not academic: the
54 model-authored pairs this replaced were right 51 times and wrong once,
and the wrong one was sedition -- exactly the pair a reviewer would have
waved through, because "IPC s.124A is now BNS s.152" is repeated
everywhere. The official table records s.124A as deleted. BNS s.152 is a
different offence with different elements.

Three things this refuses to do:

* Guess. Anything absent resolves to "no mapping known", which is visible,
  rather than to a plausible number, which is not.
* Imply equivalence. Some pairs are renumberings and some are substantive
  changes. Those carry `ingredients_changed`, taken from the source table's
  own (Change) marker, and callers must surface it.
* Collapse "not re-enacted" into "unknown". A provision the new code
  deliberately dropped has `to_section` of None and `has_successor` False,
  and that is a positive answer -- quite different from a provision this
  table has never heard of.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

# The short names used in the table, and how they appear in citations.
CODE_ALIASES: dict[str, tuple[str, ...]] = {
    "IPC": ("ipc", "indian penal code", "penal code", "i.p.c"),
    "CrPC": ("crpc", "cr.p.c", "code of criminal procedure", "criminal procedure code", "cr p c"),
    "IEA": ("iea", "indian evidence act", "evidence act"),
    "BNS": ("bns", "bharatiya nyaya sanhita", "nyaya sanhita"),
    "BNSS": ("bnss", "bharatiya nagarik suraksha sanhita", "nagarik suraksha"),
    "BSA": ("bsa", "bharatiya sakshya adhiniyam", "sakshya adhiniyam"),
}

REPLACED_BY = {"IPC": "BNS", "CrPC": "BNSS", "IEA": "BSA"}
REPLACES = {new: old for old, new in REPLACED_BY.items()}


@dataclass(frozen=True)
class SectionMapping:
    from_code: str
    from_section: str
    to_code: str
    # None where the official table records the provision as deleted -- it
    # was not carried forward at all.
    to_section: str | None
    subject: str
    ingredients_changed: bool
    note: str = ""
    review_status: str = "official_source"

    @property
    def has_successor(self) -> bool:
        return self.to_section is not None

    @property
    def is_renumbering(self) -> bool:
        """Whether the provision survived the move materially unchanged."""
        return self.has_successor and not self.ingredients_changed


_TABLE = Path(settings.legal_kb_root) / "metadata" / "section_mapping.json"


def _normalise_section(section: str) -> str:
    """"s. 154", "154.", "Section 154" all mean 154.

    Sub-section punctuation is preserved: 303(1) and 303(2) are different
    provisions with different punishments.
    """
    cleaned = str(section or "").strip().casefold()
    cleaned = re.sub(r"^(?:u/s|under\s+section|sections?|secs?\.?|ss?\.)\s*", "", cleaned)
    return cleaned.strip(" .;:")


@lru_cache(maxsize=1)
def _load() -> tuple[dict[tuple[str, str], tuple[SectionMapping, ...]], str]:
    """Both directions, each read from the source rather than derived.

    The reverse used to be inverted from the forward pair, on the reasoning
    that it is the same fact read the other way. It is not. One provision
    frequently replaces several -- BNS s.179 stands in for eleven IPC
    sections -- and inverting that asserts an equivalence the Act does not
    make. The official tables print both directions, so both are read.

    Values are tuples because a lookup legitimately has several answers.
    Returning only the first would silently narrow "this replaced eleven
    provisions" to "this replaced one".
    """
    if not _TABLE.is_file():
        return {}, "missing"
    raw = json.loads(_TABLE.read_text(encoding="utf-8"))
    status = raw.get("review_status", "unknown")
    grouped: dict[tuple[str, str], list[SectionMapping]] = {}
    for pair in raw.get("pairs", []):
        mapping = SectionMapping(
            from_code=pair["from"],
            from_section=pair["from_section"],
            to_code=pair["to"],
            to_section=pair.get("to_section"),
            subject=pair.get("subject", ""),
            ingredients_changed=bool(pair.get("ingredients_changed")),
            note=pair.get("note", ""),
            review_status=status,
        )
        key = (mapping.from_code, _normalise_section(mapping.from_section))
        grouped.setdefault(key, []).append(mapping)

    # A provision that has a successor cannot also have none. Both statements
    # appear for IEA s.65B, because a wrapped continuation line in the source
    # table carries "Deleted" against text belonging to the row above. Where
    # they conflict the successor wins: claiming a provision was not
    # re-enacted when it was is the more damaging of the two errors.
    resolved = {}
    for key, mappings in grouped.items():
        with_successor = [m for m in mappings if m.has_successor]
        resolved[key] = tuple(with_successor or mappings)
    return resolved, status


def resolve_code(text: str | None) -> str | None:
    """Which of the six codes a piece of text names, if any."""
    haystack = (text or "").casefold()
    if not haystack:
        return None
    # Longest alias first: "code of criminal procedure" must not be shadowed by
    # a shorter alias that also appears in it.
    for code, aliases in sorted(
        CODE_ALIASES.items(), key=lambda item: -max(len(a) for a in item[1])
    ):
        for alias in sorted(aliases, key=len, reverse=True):
            if alias in haystack:
                return code
    return None


def _base_section(section: str) -> str:
    return section.split("(")[0].strip()


def map_sections(code: str, section: str) -> tuple[SectionMapping, ...]:
    """Every counterpart of one provision, in whichever direction applies.

    Empty when the provision is not in the table -- "no mapping known",
    which is safe. A single entry whose `has_successor` is False is the
    other kind of answer: the table knows this provision and records that
    it was not carried forward.

    A citation without a sub-section matches every sub-section of that
    section. The BNSS concordance is printed at sub-section level, so an
    exact-match-only lookup returned nothing at all for "BNSS s.35" and
    "BNSS s.173" -- the arrest power and the FIR provision, the two most
    cited sections in this corpus. Someone who writes "s.35" means the
    section, and the section is all of its sub-sections.
    """
    index, _ = _load()
    normalised = _normalise_section(section)
    exact = index.get((code, normalised))
    if exact:
        return exact
    if "(" in normalised:
        return ()
    base = _base_section(normalised)
    collected: list[SectionMapping] = []
    for (entry_code, entry_section), mappings in index.items():
        if entry_code == code and _base_section(entry_section) == base:
            collected.extend(mappings)
    # Deterministic order: the same query must not return a different first
    # element between runs.
    return tuple(sorted(collected, key=lambda m: (m.from_section, str(m.to_section))))


def map_section(code: str, section: str) -> SectionMapping | None:
    """The single counterpart, where there is exactly one.

    None when the provision is unknown *and* when it has several
    counterparts, because there is no honest way to pick one of eleven.
    Callers that can present a list should use map_sections.
    """
    found = map_sections(code, section)
    return found[0] if len(found) == 1 else None


def map_citations(act_text: str | None, section: str | None) -> tuple[SectionMapping, ...]:
    """Map a citation as it appears in a document."""
    code = resolve_code(act_text)
    if code is None or not section:
        return ()
    return map_sections(code, section)


def map_citation(act_text: str | None, section: str | None) -> SectionMapping | None:
    code = resolve_code(act_text)
    if code is None or not section:
        return None
    return map_section(code, section)


def coverage() -> dict[str, object]:
    index, status = _load()
    forward = {code: 0 for code in REPLACED_BY}
    no_successor = 0
    for (code, _), mappings in index.items():
        if code in forward:
            forward[code] += 1
        no_successor += sum(1 for m in mappings if not m.has_successor)
    return {
        "directed_entries": len(index),
        "pairs": sum(len(v) for v in index.values()),
        "forward_pairs": forward,
        "provisions_not_re_enacted": no_successor,
        "review_status": status,
        "table": str(_TABLE),
    }
