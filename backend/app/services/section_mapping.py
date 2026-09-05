"""Bidirectional lookup between the repealed codes and their replacements.

The renumbering of the IPC, CrPC and Indian Evidence Act into the BNS, BNSS
and BSA is the highest-frequency currency question in Indian law right now,
and a police corpus is full of SOPs and circulars written against the old
numbers. A reader who lands on "section 154" needs to be told it is now BNSS
s.173, and a reader who lands on BNSS s.173 needs to be able to follow the
old case law back.

Deterministic by requirement: a table, not a prompt.

Two things this refuses to do:

* Guess. The full concordances run to hundreds of sections. A table that
  covered them by inference would look authoritative and be wrong in places
  nobody could predict, which is worse than a gap -- a gap is visible.
* Imply equivalence. Some pairs are renumberings and some are new offences
  wearing an old number's place in the sequence. Sedition is not "IPC s.124A,
  renumbered"; BNS s.152 has different elements and a different threshold.
  Those pairs carry `ingredients_changed` and callers must surface it.
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
    to_section: str
    subject: str
    ingredients_changed: bool
    note: str = ""
    review_status: str = "pending_legal_review"

    @property
    def is_renumbering(self) -> bool:
        """Whether the provision survived the move materially unchanged."""
        return not self.ingredients_changed


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
def _load() -> tuple[dict[tuple[str, str], SectionMapping], str]:
    if not _TABLE.is_file():
        return {}, "missing"
    raw = json.loads(_TABLE.read_text(encoding="utf-8"))
    status = raw.get("review_status", "unknown")
    index: dict[tuple[str, str], SectionMapping] = {}
    for pair in raw.get("pairs", []):
        mapping = SectionMapping(
            from_code=pair["from"],
            from_section=pair["from_section"],
            to_code=pair["to"],
            to_section=pair["to_section"],
            subject=pair.get("subject", ""),
            ingredients_changed=bool(pair.get("ingredients_changed")),
            note=pair.get("note", ""),
            review_status=status,
        )
        index[(mapping.from_code, _normalise_section(mapping.from_section))] = mapping
        # The reverse direction is the same fact read the other way, so it is
        # derived rather than typed twice -- two hand-written directions drift.
        index[(mapping.to_code, _normalise_section(mapping.to_section))] = SectionMapping(
            from_code=mapping.to_code,
            from_section=mapping.to_section,
            to_code=mapping.from_code,
            to_section=mapping.from_section,
            subject=mapping.subject,
            ingredients_changed=mapping.ingredients_changed,
            note=mapping.note,
            review_status=status,
        )
    return index, status


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


def map_section(code: str, section: str) -> SectionMapping | None:
    """The counterpart of one provision, in whichever direction applies.

    Returns None when the pair is not in the table. That is a real answer:
    "no mapping known" is safe, and a guessed one is not.
    """
    index, _ = _load()
    return index.get((code, _normalise_section(section)))


def map_citation(act_text: str | None, section: str | None) -> SectionMapping | None:
    """Map a citation as it appears in a document."""
    code = resolve_code(act_text)
    if code is None or not section:
        return None
    return map_section(code, section)


def coverage() -> dict[str, object]:
    index, status = _load()
    forward = {code: 0 for code in REPLACED_BY}
    for (code, _), _mapping in index.items():
        if code in forward:
            forward[code] += 1
    return {
        "directed_entries": len(index),
        "forward_pairs": forward,
        "review_status": status,
        "table": str(_TABLE),
    }
