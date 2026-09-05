"""How a citation's currency is described to the reader.

Three call sites built this expression independently -- Deep, Fast and defence
strategy -- so a fourth state had to be added in three places or it would show
in one lane and not another.
"""

from __future__ import annotations

from typing import Any

from app.services.currency import CurrencyStatus, resolve_currency

CurrentStatus = str


def citation_labels(payload: dict[str, Any]) -> dict[str, Any]:
    """Everything a citation needs to say about currency, in one place.

    Returns the fields an AgentCitation carries, so the three lanes cannot
    render different subsets of the same facts.
    """
    from app.services.repeal_labels import RepealLabel, repeal_notice

    status, replaced_by, repealed_on = citation_currency(payload)
    notice = repeal_notice(payload)

    mappings = [
        {
            "from_code": mapping.from_code,
            "from_section": mapping.from_section,
            "to_code": mapping.to_code,
            "to_section": mapping.to_section,
            "subject": mapping.subject,
            "ingredients_changed": mapping.ingredients_changed,
            "note": mapping.note,
        }
        for mapping in notice.mappings
    ]

    # Label B carries its own successor and date; Label A's come from currency.
    if notice.label is RepealLabel.CONCERNS_REPEALED_PROVISION:
        replaced_by = replaced_by or notice.replaced_by
        repealed_on = repealed_on or notice.repealed_on

    return {
        "current_status": status,
        "replaced_by": replaced_by,
        "repealed_on": repealed_on,
        "repeal_label": str(notice.label),
        "section_mappings": mappings,
        "unmapped_repealed_provisions": list(notice.unmapped_provisions),
        "mapping_review_status": notice.review_status or None,
    }


def citation_currency(payload: dict[str, Any]) -> tuple[CurrentStatus, str | None, str | None]:
    """The status to show, and the successor Act when one exists.

    Delegates to `resolve_currency` rather than reading `is_superseded` and
    `is_current` itself. Both fields are effectively never true in this corpus
    -- `is_current` is false for every document by design -- so reading them
    here returned "status_unverified" for a repealed Act as readily as for a
    circular nobody has checked. That was the same bug found six other times.

    `repealed` and `superseded` stay distinct. A repeal that saves prior
    conduct still governs a period, so it is cited with the repeal stated; an
    instrument superseded with no savings governs nothing and may not ground a
    published claim at all.
    """
    decision = resolve_currency(payload)

    if decision.status is CurrencyStatus.SUPERSEDED:
        status = "repealed" if decision.saves_prior_conduct else "superseded"
        return status, decision.superseded_by, decision.effective

    if decision.status is CurrencyStatus.IN_FORCE:
        return "current", None, None

    if payload.get("corpus_scope") == "private_case":
        return "not_applicable", None, None

    return "status_unverified", None, None
