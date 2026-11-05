"""Chain of custody, remand arithmetic and the case diary's gaps.

All of it is arithmetic and string comparison on what the officer recorded. A broken
chain is not an inadmissible exhibit, and a missing diary day is not a lapse, only a
page the record does not have. Each says what it found and leaves the conclusion to
the reader.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from app.core.india_time import india_date
from app.models.enums import OffenceGravity

__all__ = [
    "ChainFinding",
    "ChainState",
    "CustodyHop",
    "RemandPeriod",
    "RemandSummary",
    "analyse_chain",
    "diary_gaps",
    "remand_summary",
]


class ChainState(StrEnum):
    CONTINUOUS = "continuous"
    BROKEN = "broken"
    CANNOT_BE_DETERMINED = "cannot_be_determined"


@dataclass(frozen=True)
class CustodyHop:
    id: str
    occurred_at: datetime
    from_person: str
    to_person: str
    corrects_event_id: str | None = None


@dataclass(frozen=True)
class ChainFinding:
    state: ChainState
    current_holder: str | None
    issues: tuple[str, ...]


def _same(left: str | None, right: str | None) -> bool:
    return " ".join((left or "").split()).casefold() == " ".join((right or "").split()).casefold()


def analyse_chain(
    *,
    seized_by: str | None,
    seized_at: datetime | None,
    hops: list[CustodyHop],
) -> ChainFinding:
    """Whether each hand-over starts from whoever held the item last.

    Names are compared as written, ignoring case and spacing. "SI Rao" and "Rao" read
    as a break on purpose: the two entries do not say the same person held it, and a
    court reading them has the same difficulty.
    """
    replaced = {hop.corrects_event_id for hop in hops if hop.corrects_event_id}
    live = sorted((hop for hop in hops if hop.id not in replaced), key=lambda hop: hop.occurred_at)

    if not seized_by or seized_at is None:
        return ChainFinding(
            ChainState.CANNOT_BE_DETERMINED,
            live[-1].to_person if live else seized_by,
            ("Who seized the item, or when, is not recorded, so the chain has no starting point.",),
        )

    issues: list[str] = []
    holder = seized_by
    previous_at = seized_at
    for hop in live:
        when = hop.occurred_at.isoformat(timespec="minutes")
        if hop.occurred_at < previous_at:
            issues.append(
                f"The hand-over to {hop.to_person} at {when} is dated before the entry it follows."
            )
        if not _same(hop.from_person, holder):
            issues.append(
                f"The hand-over at {when} is from {hop.from_person}, but the last recorded holder is {holder}."
            )
        holder = hop.to_person
        previous_at = hop.occurred_at

    return ChainFinding(
        ChainState.BROKEN if issues else ChainState.CONTINUOUS,
        holder,
        tuple(issues),
    )


@dataclass(frozen=True)
class RemandPeriod:
    custody_type: str
    from_date: date
    to_date: date


@dataclass(frozen=True)
class RemandSummary:
    police_days_used: int
    police_days_left: int
    judicial_days: int
    first_remand_date: date | None
    # Last date of the initial forty or sixty days, within which police custody
    # can fall. None where it cannot be computed.
    police_custody_window_ends: date | None
    window_days: int | None
    undetermined_because: str
    findings: tuple[str, ...]


POLICE_CUSTODY_LIMIT_DAYS = 15


def _days(period: RemandPeriod) -> int:
    return (period.to_date - period.from_date).days + 1


def remand_summary(
    periods: list[RemandPeriod],
    *,
    first_remand_at: datetime | None,
    gravity: OffenceGravity,
    today: date,
) -> RemandSummary:
    """s.187(2): police custody within the first forty or sixty days, fifteen in all.

    Both ends of a period count as whole days. That is the reading which can only
    warn early; how a court would count a part-day is a question for the prosecutor,
    and the screen says so.
    """
    police = [p for p in periods if p.custody_type == "police"]
    judicial = [p for p in periods if p.custody_type == "judicial"]
    used = sum(_days(p) for p in police)
    earliest = min((p.from_date for p in periods), default=None)
    first = india_date(first_remand_at) if first_remand_at else earliest

    findings: list[str] = []
    if used > POLICE_CUSTODY_LIMIT_DAYS:
        findings.append(
            f"The recorded police custody totals {used} days, more than the fifteen s.187(2) allows."
        )

    window_days: int | None = None
    window_ends: date | None = None
    undetermined = ""
    if first is None:
        undetermined = "no first remand date is recorded"
    elif gravity is OffenceGravity.UNKNOWN:
        undetermined = (
            "the offence's gravity is not recorded, so it is unknown whether the period "
            "is the initial forty or sixty days"
        )
    else:
        window_days = 60 if gravity is OffenceGravity.DEATH_LIFE_OR_TEN_YEARS_OR_MORE else 40
        window_ends = first + timedelta(days=window_days - 1)
        for period in police:
            if period.to_date > window_ends:
                findings.append(
                    f"Police custody to {period.to_date.isoformat()} runs past the end of the "
                    f"initial {window_days} days on {window_ends.isoformat()}."
                )
        if today > window_ends and used < POLICE_CUSTODY_LIMIT_DAYS:
            findings.append(
                f"The initial {window_days} days ended on {window_ends.isoformat()}; the unused "
                "police custody cannot now be sought under s.187(2) as worded."
            )

    return RemandSummary(
        police_days_used=used,
        police_days_left=max(POLICE_CUSTODY_LIMIT_DAYS - used, 0),
        judicial_days=sum(_days(p) for p in judicial),
        first_remand_date=first,
        police_custody_window_ends=window_ends,
        window_days=window_days,
        undetermined_because=undetermined,
        findings=tuple(findings),
    )


def diary_gaps(entry_dates: list[date], *, until: date) -> list[date]:
    """Days between the first entry and `until` with no diary entry.

    s.192(1) says "day by day". A day with nothing to report may be a day nothing
    happened, so these are shown as days without an entry, not as lapses.
    """
    if not entry_dates:
        return []
    have = set(entry_dates)
    start = min(have)
    span = (until - start).days
    return [start + timedelta(days=i) for i in range(span + 1) if start + timedelta(days=i) not in have]
