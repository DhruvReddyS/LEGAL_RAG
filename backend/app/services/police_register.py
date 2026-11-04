"""Deadlines across cases, and what each one's state actually means.

Four words carry the feature, and they are not synonyms:

* due: the limit has not passed and nobody has recorded the step.
* overdue: the limit has passed and nobody has recorded the step. It may have been
  done without being written down, so this is an open question, not a finding.
* breached: the step is on record, and the record shows it was taken after the limit.
* unknown: the limit cannot be computed, or the record cannot settle it. Never shown
  as passed or failed.

"met" exists because a register that drops a satisfied duty cannot show one was met.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.services.investigation_timeline import Deadline, InvestigationFacts

__all__ = [
    "IMMINENT_HOURS",
    "RegisterRow",
    "RegisterState",
    "classify",
    "derived_completions",
    "register_rows",
    "search_record_deadline",
    "sort_rows",
    "summarise",
]

# How close counts as "imminent". The shortest limits in the register are
# twenty-four hours, so a shorter window would catch them too late.
IMMINENT_HOURS = 48


class RegisterState(StrEnum):
    BREACHED = "breached"
    OVERDUE = "overdue"
    DUE = "due"
    MET = "met"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RegisterRow:
    case_id: str
    case_title: str
    key: str
    obligation: str
    provision: str
    actor: str
    consequence: str
    computed_from: str
    due_at: datetime | None
    state: RegisterState
    state_reason: str
    is_earliest_possible: bool
    is_imminent: bool
    completed_at: datetime | None
    completion_note: str
    completion_is_derived: bool
    notes: tuple[str, ...]

    @property
    def is_officer_duty(self) -> bool:
        return self.actor == "investigating_officer"


def classify(
    deadline: Deadline,
    completed_at: datetime | None,
    now: datetime,
    *,
    imminent_hours: int = IMMINENT_HOURS,
) -> tuple[RegisterState, str, bool]:
    """State, the reason in words, and whether it needs attention soon."""
    due = deadline.due_at
    if due is None:
        if completed_at is not None:
            return (
                RegisterState.UNKNOWN,
                f"A completion is recorded, but the limit cannot be computed: "
                f"{deadline.undetermined_because}.",
                False,
            )
        return (RegisterState.UNKNOWN, f"Cannot be determined: {deadline.undetermined_because}.", False)

    if completed_at is not None:
        if completed_at <= due:
            return RegisterState.MET, "Recorded as done within the limit.", False
        if deadline.is_earliest_possible:
            # s.58 and s.78 exclude the journey, which this cannot know. Done after
            # the earliest expiry is neither shown to be late nor shown to be on time.
            return (
                RegisterState.UNKNOWN,
                "Recorded as done after the earliest the period could expire. Journey "
                "time is excluded and is not recorded, so this cannot be settled here.",
                False,
            )
        return RegisterState.BREACHED, "Recorded as done after the limit passed.", False

    if now > due:
        return (
            RegisterState.OVERDUE,
            "The limit has passed and no completion is recorded. Record it if it was done.",
            False,
        )
    return (
        RegisterState.DUE,
        "Not yet expired, and no completion is recorded.",
        due - now <= timedelta(hours=imminent_hours),
    )


def derived_completions(facts: InvestigationFacts) -> dict[str, datetime]:
    """Completions the recorded dates already establish.

    Only where the date is the act itself. A first remand follows production, and a
    forwarded report is what ss.187(3) and 193(2) ask for. accused_produced_at is not
    used: s.230 means production after the report, not first production.
    """
    derived: dict[str, datetime] = {}
    if facts.first_remand_at:
        derived["production_before_magistrate"] = facts.first_remand_at
    if facts.police_report_forwarded_at:
        derived["default_bail_entitlement"] = facts.police_report_forwarded_at
        derived["investigation_completion"] = facts.police_report_forwarded_at
    return derived


def search_record_deadline(
    search_id: str,
    place: str,
    grounds_recorded_at: datetime | None,
) -> Deadline:
    """s.185(5), for one search. The limit runs from the record, which may be absent."""
    return Deadline(
        key=f"search_record_to_magistrate:{search_id}",
        obligation="Send copies of the s.185 record of this search to the nearest Magistrate.",
        provision="BNSS s.185(5)",
        due_at=grounds_recorded_at + timedelta(hours=48) if grounds_recorded_at else None,
        consequence="Forthwith, and not later than forty-eight hours.",
        computed_from="forty-eight hours from the record of the grounds of belief",
        undetermined_because="" if grounds_recorded_at else "the time the grounds were recorded is not on the search record",
        # Kept out of the obligation: a supervisor sees obligations, not where a search was.
        notes=(f"Search at {place}.",),
    )


def register_rows(
    *,
    case_id: str,
    case_title: str,
    deadlines: list[Deadline],
    completions: dict[str, tuple[datetime, str]],
    derived: dict[str, datetime],
    now: datetime,
    imminent_hours: int = IMMINENT_HOURS,
) -> list[RegisterRow]:
    rows: list[RegisterRow] = []
    for deadline in deadlines:
        explicit = completions.get(deadline.key)
        # What the officer stated takes precedence over what the dates imply.
        completed_at = explicit[0] if explicit else derived.get(deadline.key)
        state, reason, imminent = classify(
            deadline, completed_at, now, imminent_hours=imminent_hours
        )
        rows.append(
            RegisterRow(
                case_id=case_id,
                case_title=case_title,
                key=deadline.key,
                obligation=deadline.obligation,
                provision=deadline.provision,
                actor=deadline.actor,
                consequence=deadline.consequence,
                computed_from=deadline.computed_from,
                due_at=deadline.due_at,
                state=state,
                state_reason=reason,
                is_earliest_possible=deadline.is_earliest_possible,
                is_imminent=imminent,
                completed_at=completed_at,
                completion_note=explicit[1] if explicit else "",
                completion_is_derived=explicit is None and completed_at is not None,
                notes=deadline.notes,
            )
        )
    return rows


_RANK = {
    RegisterState.OVERDUE: 0,
    RegisterState.DUE: 1,
    RegisterState.BREACHED: 2,
    RegisterState.UNKNOWN: 3,
    RegisterState.MET: 4,
}


def sort_rows(rows: list[RegisterRow]) -> list[RegisterRow]:
    """Most urgent first. A duty somebody else owes sinks below the officer's own."""

    def key(row: RegisterRow) -> tuple:
        if row.state is RegisterState.DUE and row.is_imminent:
            rank = 0
        else:
            rank = _RANK[row.state]
        due = row.due_at.timestamp() if row.due_at else float("inf")
        return (0 if row.is_officer_duty else 1, rank, due, row.case_title, row.key)

    return sorted(rows, key=key)


def summarise(rows: list[RegisterRow]) -> dict[str, int]:
    """Counts of the officer's own duties, so a Magistrate's lapse is not reported
    as a police breach."""
    counts = {state.value: 0 for state in RegisterState}
    counts["imminent"] = 0
    counts["not_officer_duty"] = 0
    for row in rows:
        if not row.is_officer_duty:
            counts["not_officer_duty"] += 1
            continue
        counts[row.state.value] += 1
        if row.is_imminent:
            counts["imminent"] += 1
    return counts
