"""Whether a cited authority is still law.

This replaces seven separate reads of `payload["is_superseded"] is True`.
That expression has the shape this codebase has been bitten by repeatedly: it
is permissive when the value is absent. The field is written by ingestion and
was added after the live index was built, so it holds `None` for all 25,517
points -- every one of those seven guards evaluates false forever while
reading as protective.

The mirror image is live in the same field. `RetrievalFilters` matched
`is_superseded == False`, and `None` is not `False`, so enabling that filter
would have excluded the entire corpus. One field, treated as a boolean, wrong
in both directions.

So currency is resolved rather than read: from a curated table of authorities,
then from the repeal table, then from the stored flag, and it always returns
one of three answers. `unverified` is a real answer and is labelled as one. It
is never silently upgraded to `in_force`.

Deterministic by requirement: no model is consulted here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.ingestion.supersession import replacement_for


class CurrencyStatus(StrEnum):
    IN_FORCE = "in_force"
    SUPERSEDED = "superseded"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class CurrencyDecision:
    status: CurrencyStatus
    superseded_by: str | None = None
    effective: str | None = None
    basis: str = ""
    source: str = "default"
    # Whether the repeal leaves a period the instrument still governs. An
    # offence committed on 30 June 2024 is tried under the Penal Code, so that
    # repeal saves prior conduct. A model manual replaced by a later edition
    # saves nothing -- there is no period it still governs.
    saves_prior_conduct: bool = False

    @property
    def is_superseded(self) -> bool:
        """True only when supersession is positively established.

        Deliberately not `status != IN_FORCE`. An unverified authority is not
        known to be superseded, and blocking it would empty the corpus.
        """
        return self.status is CurrencyStatus.SUPERSEDED

    @property
    def may_ground_a_published_claim(self) -> bool:
        """Whether a user-facing legal proposition may rest on this source.

        Three cases, and collapsing any two of them gets a real question wrong:

        * superseded with no savings -- may not. There is no longer any set of
          facts it governs, so citing it can only mislead.
        * superseded but saving prior conduct -- may, provided the repeal is
          stated. Refusing here would decline to answer about an offence
          committed before July 2024 under the law that actually governs it.
        * unverified -- may, with the label. The corpus cannot verify most of
          itself, and refusing everything unverified abstains on everything.

        The label is not optional in the second and third cases, which is why
        callers take the whole decision rather than this flag on its own.
        """
        if self.is_superseded:
            return self.saves_prior_conduct
        return True

    @property
    def requires_a_currency_label(self) -> bool:
        """Publishing this source without saying what it is would mislead."""
        return self.status is not CurrencyStatus.IN_FORCE


_DEFAULT_TABLE = Path(settings.legal_kb_root) / "metadata" / "currency_status.json"


@lru_cache(maxsize=1)
def _entries() -> tuple[tuple[str, CurrencyDecision], ...]:
    """Curated entries, longest prefix first so a specific rule wins.

    The 1898 Code of Criminal Procedure and the general Code of Criminal
    Procedure rule both match the same title, and they name different
    successors fifty years apart.
    """
    path = _DEFAULT_TABLE
    if not path.is_file():
        return ()
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows: list[tuple[str, CurrencyDecision]] = []
    for entry in raw.get("entries", []):
        prefix = str(entry["starts_with"]).casefold().strip()
        rows.append(
            (
                prefix,
                CurrencyDecision(
                    status=CurrencyStatus(entry["status"]),
                    superseded_by=entry.get("superseded_by"),
                    effective=entry.get("effective"),
                    basis=entry.get("basis", ""),
                    source="curated",
                    saves_prior_conduct=bool(entry.get("saves_prior_conduct", False)),
                ),
            )
        )
    rows.sort(key=lambda row: len(row[0]), reverse=True)
    return tuple(rows)


def _curated(*names: str | None) -> CurrencyDecision | None:
    for name in names:
        cleaned = (name or "").casefold().strip()
        if not cleaned:
            continue
        for prefix, decision in _entries():
            if cleaned.startswith(prefix):
                return decision
    return None


def resolve_currency(payload: dict[str, Any]) -> CurrencyDecision:
    """The status of the authority a chunk came from.

    Order matters and is from most to least trustworthy:

    1. The curated table, which a person reviewed.
    2. The repeal table, which knows the three codes replaced in July 2024.
    3. The stored `is_superseded` flag, but only when it is exactly True --
       `None` means the index predates the field, not that the source is
       current.
    4. Otherwise unverified, and said so.

    Private case evidence is not legislation and has no currency; it resolves
    to unverified rather than being forced into a statutory answer.
    """
    if payload.get("corpus_scope") == "private_case":
        return CurrencyDecision(
            status=CurrencyStatus.UNVERIFIED,
            basis="Private case evidence is not legislation and has no currency.",
            source="private_case",
        )

    name_fields = (payload.get("act_name"), payload.get("title"))

    curated = _curated(*name_fields)
    if curated is not None:
        return curated

    replacement = replacement_for(*name_fields)
    if replacement is not None:
        return CurrencyDecision(
            status=CurrencyStatus.SUPERSEDED,
            superseded_by=replacement.replaced_by,
            effective=replacement.repealed_on,
            basis="Repealed Act, resolved from the repeal table.",
            source="repeal_table",
            saves_prior_conduct=True,
        )

    # A successor named on the point itself. Ingestion writes this from the
    # repeal table, but a curated addition can set it for an instrument the
    # tables above do not know, and dropping it would silently discard the
    # only currency information such a point carries.
    stored_successor = payload.get("replaced_by") or payload.get("superseded_by")
    if stored_successor:
        return CurrencyDecision(
            status=CurrencyStatus.SUPERSEDED,
            superseded_by=str(stored_successor),
            effective=payload.get("repealed_on") or payload.get("superseded_effective"),
            basis="Successor named on the indexed point.",
            source="payload_successor",
            saves_prior_conduct=bool(payload.get("saves_prior_conduct", False)),
        )

    # Written by ingestion. Only an explicit True counts: the live index holds
    # None for every point, and reading None as "not superseded" is the bug
    # this module exists to remove.
    if payload.get("is_superseded") is True:
        return CurrencyDecision(
            status=CurrencyStatus.SUPERSEDED,
            superseded_by=payload.get("replaced_by") or payload.get("superseded_by"),
            basis="Marked superseded during ingestion.",
            source="payload_flag",
            saves_prior_conduct=False,
        )

    if payload.get("is_current") is True:
        return CurrencyDecision(
            status=CurrencyStatus.IN_FORCE,
            basis="Marked current during ingestion.",
            source="payload_flag",
        )

    return CurrencyDecision(
        status=CurrencyStatus.UNVERIFIED,
        basis="No curated status for this authority, and ingestion did not establish one.",
        source="default",
    )


def curated_coverage() -> dict[str, Any]:
    """What the table covers, for reporting rather than for decisions."""
    entries = _entries()
    return {
        "curated_entries": len(entries),
        "in_force": sum(1 for _, d in entries if d.status is CurrencyStatus.IN_FORCE),
        "superseded": sum(1 for _, d in entries if d.status is CurrencyStatus.SUPERSEDED),
        "table": str(_DEFAULT_TABLE),
    }
