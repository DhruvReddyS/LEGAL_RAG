"""Statutory deadlines in an investigation, computed rather than recalled.

This is the deterministic core of the police module. Every date here comes
out of calendar arithmetic on a provision of the BNSS -- no model is
consulted, and none should be. A model that is fluent about "the ninety-day
period" and wrong about when it starts produces an answer that reads
correct and costs someone their liberty, or hands an accused a default-bail
entitlement nobody noticed.

Three things this refuses to do:

* It will not guess an offence's gravity. Without it the s.187(3) period is
  unknown, and the deadline says so instead of quietly assuming sixty days
  -- the assumption that produces the later date, and so the one that hides
  a default-bail entitlement that has already accrued.
* It will not present s.58's twenty-four hours as an exact wall-clock
  moment. The Sanhita excludes journey time from the place of arrest, which
  this cannot know, so the computed time is marked as the earliest the
  period could expire.
* It will not run the s.187(3) period from the arrest. It runs from the
  first remand. Using the arrest instead shortens the period and is the
  single most common error in this calculation.

Every deadline carries the provision it was computed from, so the output
can be checked against the Act rather than trusted.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum

__all__ = [
    "Deadline",
    "InvestigationFacts",
    "OffenceGravity",
    "investigation_deadlines",
    "add_calendar_months",
]


class OffenceGravity(Enum):
    """The distinction s.187(3) turns on, and nothing finer.

    ``UNKNOWN`` is a real member rather than a missing value. The whole
    point is that an uncatalogued offence produces a stated unknown instead
    of a plausible date.
    """

    DEATH_LIFE_OR_TEN_YEARS_OR_MORE = "death_life_or_ten_years_or_more"
    OTHER = "other"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class InvestigationFacts:
    """What the calculation needs, each part optional and independently used.

    A deadline whose inputs are absent is still returned -- as undetermined,
    naming what is missing. Dropping it from the list would let an unrecorded
    arrest time read as "no production deadline applies".
    """

    information_recorded_at: datetime | None = None
    arrested_at: datetime | None = None
    first_remand_at: datetime | None = None
    accused_produced_at: datetime | None = None
    death_occurred_at: datetime | None = None
    gravity: OffenceGravity = OffenceGravity.UNKNOWN
    # s.193(2) lists the BNS sexual offences and the POCSO sections that
    # carry the two-month completion rule. It is a flag rather than an
    # inferred property because inferring it from free text is exactly the
    # kind of guess this module exists to avoid.
    is_listed_sexual_offence: bool = False
    preliminary_enquiry_started_at: datetime | None = None
    is_unnatural_death: bool = False


@dataclass(frozen=True)
class Deadline:
    """One statutory obligation, with the provision that imposes it."""

    key: str
    obligation: str
    provision: str
    due_at: datetime | None
    consequence: str
    computed_from: str
    # True where the Sanhita's period cannot be pinned to a wall-clock
    # instant from the facts available -- s.58 excludes journey time, so the
    # figure is the earliest the period could expire, not the limit itself.
    is_earliest_possible: bool = False
    undetermined_because: str = ""

    @property
    def determined(self) -> bool:
        return self.due_at is not None

    def remaining(self, now: datetime) -> timedelta | None:
        return None if self.due_at is None else self.due_at - now

    def is_breached(self, now: datetime) -> bool | None:
        """None where the deadline could not be computed.

        Returning False for an undetermined deadline would report compliance
        that was never established -- the same absence-read-as-a-value
        mistake that once turned an unreadable ledger into "0 documents".
        """
        if self.due_at is None:
            return None
        return now > self.due_at


def add_calendar_months(moment: datetime, months: int) -> datetime:
    """Add calendar months, clamping to the end of a shorter month.

    s.193(2) says "two months", not "sixty days", and the two differ by up
    to two days -- which is the difference between a completed investigation
    and a breach. Naive arithmetic on 31 December would produce 31 February.
    """
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


_UNKNOWN_GRAVITY = (
    "the offence's gravity is not recorded, so it is unknown whether the "
    "s.187(3) period is ninety or sixty days"
)


def investigation_deadlines(facts: InvestigationFacts) -> list[Deadline]:
    """Every statutory deadline the recorded facts bear on.

    Deadlines that do not apply on these facts are omitted; deadlines that
    apply but cannot be computed are returned undetermined, naming what is
    missing. The two are different findings and the caller must be able to
    tell them apart.
    """
    out: list[Deadline] = []

    def add(
        key: str,
        obligation: str,
        provision: str,
        due_at: datetime | None,
        consequence: str,
        computed_from: str,
        *,
        earliest: bool = False,
        missing: str = "",
    ) -> None:
        out.append(
            Deadline(
                key=key,
                obligation=obligation,
                provision=provision,
                due_at=due_at,
                consequence=consequence,
                computed_from=computed_from,
                is_earliest_possible=earliest and due_at is not None,
                undetermined_because=missing if due_at is None else "",
            )
        )

    # ---- s.58: production before a Magistrate within twenty-four hours
    if facts.arrested_at:
        add(
            "production_before_magistrate",
            "Produce the arrested person before a Magistrate.",
            "BNSS s.58",
            facts.arrested_at + timedelta(hours=24),
            "Detention beyond this without an order under s.187 is unlawful.",
            "twenty-four hours from the time of arrest",
            earliest=True,
        )

    # ---- s.187(3): the default-bail period
    if facts.first_remand_at or facts.arrested_at:
        if facts.gravity is OffenceGravity.UNKNOWN:
            add(
                "default_bail_entitlement",
                "Complete the investigation and file the report, or the accused "
                "becomes entitled to release on bail.",
                "BNSS s.187(3)",
                None,
                "On expiry the accused shall be released on bail if prepared to "
                "furnish it. The entitlement is indefeasible once it accrues.",
                "not computed",
                missing=_UNKNOWN_GRAVITY,
            )
        elif facts.first_remand_at is None:
            add(
                "default_bail_entitlement",
                "Complete the investigation and file the report, or the accused "
                "becomes entitled to release on bail.",
                "BNSS s.187(3)",
                None,
                "On expiry the accused shall be released on bail if prepared to "
                "furnish it. The entitlement is indefeasible once it accrues.",
                "not computed",
                missing=(
                    "the date of first remand is not recorded; the period runs "
                    "from first remand, not from the arrest, and computing it "
                    "from the arrest would shorten it"
                ),
            )
        else:
            days = (
                90
                if facts.gravity is OffenceGravity.DEATH_LIFE_OR_TEN_YEARS_OR_MORE
                else 60
            )
            add(
                "default_bail_entitlement",
                "Complete the investigation and file the report, or the accused "
                "becomes entitled to release on bail.",
                f"BNSS s.187(3)({'i' if days == 90 else 'ii'})",
                facts.first_remand_at + timedelta(days=days),
                "On expiry the accused shall be released on bail if prepared to "
                "furnish it. The entitlement is indefeasible once it accrues.",
                f"{days} days from the date of first remand",
            )

    # ---- s.173(3)(i): preliminary enquiry within fourteen days
    if facts.preliminary_enquiry_started_at:
        add(
            "preliminary_enquiry",
            "Conclude the preliminary enquiry into whether a prima facie case exists.",
            "BNSS s.173(3)(i)",
            facts.preliminary_enquiry_started_at + timedelta(days=14),
            "The enquiry may not run beyond fourteen days; proceed to "
            "investigation or close it.",
            "fourteen days from the start of the preliminary enquiry",
        )

    # ---- s.193(2): two months for the listed sexual offences
    if facts.is_listed_sexual_offence:
        if facts.information_recorded_at is None:
            add(
                "investigation_completion",
                "Complete the investigation.",
                "BNSS s.193(2)",
                None,
                "The Sanhita fixes two months for these offences.",
                "not computed",
                missing="the date the information was recorded is not known",
            )
        else:
            add(
                "investigation_completion",
                "Complete the investigation into the listed sexual offence.",
                "BNSS s.193(2)",
                add_calendar_months(facts.information_recorded_at, 2),
                "The Sanhita requires completion within two months of recording "
                "the information.",
                "two calendar months from the date the information was recorded",
            )

    # ---- s.193(3)(ii): tell the informant or victim where it has got to
    if facts.information_recorded_at:
        add(
            "victim_progress_update",
            "Inform the informant or victim of the progress of the investigation.",
            "BNSS s.193(3)(ii)",
            facts.information_recorded_at + timedelta(days=90),
            "The update is mandatory and may be given by any means, including "
            "electronic communication.",
            "ninety days from the date the information was recorded",
        )

    # ---- s.184: medical examination of the victim
    if facts.is_listed_sexual_offence and facts.information_recorded_at:
        add(
            "victim_medical_examination",
            "Send the woman to a registered medical practitioner for examination.",
            "BNSS s.184",
            facts.information_recorded_at + timedelta(hours=24),
            "Delay degrades the medical evidence and is itself a lapse.",
            "twenty-four hours from receiving the information",
        )

    # ---- s.194: unnatural death
    if facts.is_unnatural_death and facts.death_occurred_at:
        add(
            "post_mortem_referral",
            "Forward the body for examination by the Civil Surgeon or other "
            "qualified medical person.",
            "BNSS s.194(6)",
            facts.death_occurred_at + timedelta(hours=24),
            "The body must be forwarded within twenty-four hours of the death "
            "unless it is impossible to do so.",
            "twenty-four hours from the death",
        )
        add(
            "inquest_report_to_magistrate",
            "Forward the inquest report to the District or Sub-divisional Magistrate.",
            "BNSS s.194(2)",
            facts.death_occurred_at + timedelta(hours=24),
            "The signed report must reach the Magistrate within twenty-four hours.",
            "twenty-four hours from the death",
        )

    # ---- s.230: supply of the report and documents to the accused
    if facts.accused_produced_at:
        add(
            "supply_of_documents",
            "Furnish the accused and the victim's advocate with the police report, "
            "the FIR, the s.180(3) statements and the s.183 confessions, free of cost.",
            "BNSS s.230",
            facts.accused_produced_at + timedelta(days=14),
            "Supply must be without delay and in no case beyond fourteen days.",
            "fourteen days from the production or appearance of the accused",
        )

    return out


def breached(deadlines: list[Deadline], now: datetime) -> list[Deadline]:
    """Only those positively past due.

    Undetermined deadlines are excluded here and must be surfaced separately
    -- an unknown is not a pass.
    """
    return [d for d in deadlines if d.is_breached(now) is True]


def undetermined(deadlines: list[Deadline]) -> list[Deadline]:
    return [d for d in deadlines if d.due_at is None]
