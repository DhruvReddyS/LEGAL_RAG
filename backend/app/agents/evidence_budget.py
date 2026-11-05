"""How much of each passage the model may read, for reasoning and for verifying.

A flat 1,800 characters was set when passages were smaller. On v6, 30% of Act passages
are longer, and BNSS s.35 is 5,544 characters, so the model saw a third of the section
and could not name grounds it had never read. The verifier was cut the same way, which
would reject a true claim drawn from the tail. A list in a statute is the part a reader
most needs whole, so primary law gets the room, and other material gives some back to
keep the prompt within what fits.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

DEFAULT_CHARACTERS = 1800
PRIMARY_LAW_CHARACTERS = 6000
PRIMARY_LAW_TOTAL_CHARACTERS = 12000
SHARING_CHARACTERS = 1200


def _is_primary_law(payload: dict[str, Any]) -> bool:
    return (
        str(payload.get("document_type")) == "bare_act"
        or str(payload.get("source_type")) == "CONSTITUTION"
    )


def character_limits(hits: Iterable[Any]) -> dict[str, int]:
    """Characters per chunk id. Earlier hits are served first, as they ranked higher."""
    chunks = list(hits)
    primary = [hit for hit in chunks if _is_primary_law(hit.payload)]
    if not primary:
        return {str(hit.payload.get("chunk_id")): DEFAULT_CHARACTERS for hit in chunks}
    limits = {str(hit.payload.get("chunk_id")): SHARING_CHARACTERS for hit in chunks}
    remaining = PRIMARY_LAW_TOTAL_CHARACTERS
    for hit in primary:
        wanted = min(len(str(hit.payload.get("text") or "")), PRIMARY_LAW_CHARACTERS)
        granted = max(min(wanted, remaining), SHARING_CHARACTERS)
        limits[str(hit.payload.get("chunk_id"))] = granted
        remaining = max(0, remaining - granted)
    return limits
