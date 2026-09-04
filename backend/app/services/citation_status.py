"""How a citation's currency is described to the reader.

Three call sites built this expression independently -- Deep, Fast and defence
strategy -- so a fourth state had to be added in three places or it would show
in one lane and not another.
"""

from __future__ import annotations

from typing import Any

from app.ingestion.supersession import replacement_for

CurrentStatus = str


def citation_currency(payload: dict[str, Any]) -> tuple[CurrentStatus, str | None, str | None]:
    """The status to show, and the successor Act when one exists.

    `repealed` is deliberately distinct from `superseded`. Superseded means the
    source cannot ground a published claim at all. A repealed Act still governs
    conduct from before its repeal -- an offence committed on 30 June 2024 is
    tried under the Indian Penal Code -- so it is cited, with the repeal and
    its replacement stated.
    """
    replaced_by = payload.get("replaced_by") or None
    repealed_on = payload.get("repealed_on") or None
    if not replaced_by:
        # An index built before the field existed carries neither, so the Act's
        # name is read instead -- the same source the ranking preference uses.
        # Without this the two halves disagree: a repealed provision would be
        # demoted in the ordering and then shown to the reader unlabelled,
        # which is the half that actually matters.
        derived = replacement_for(payload.get("act_name"), payload.get("title"))
        if derived is not None:
            replaced_by, repealed_on = derived.replaced_by, derived.repealed_on
    if payload.get("is_superseded") is True:
        return "superseded", replaced_by, repealed_on
    if replaced_by:
        return "repealed", replaced_by, repealed_on
    if payload.get("is_current") is True:
        return "current", None, None
    if payload.get("corpus_scope") == "private_case":
        return "not_applicable", None, None
    return "status_unverified", None, None
