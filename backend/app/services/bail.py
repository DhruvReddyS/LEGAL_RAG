"""Bail routes under the BNSS, read from the text and computed from dates.

No model reads the facts and none writes the findings. Every status below is
reached by arithmetic and by the words of a provision pinned in
`advocate_provisions`, so a finding can be checked against the Act.

Three things this refuses to do, each for the reason the police timeline
refuses the same thing:

* It will not guess. A fact nobody entered produces a stated unknown, naming
  the fact, never a default that happens to make a date computable.
* It will not say what a court will do. "Entitled on the text" is what the
  words of a section say on the facts entered. Whether a court so orders is
  not computed and is not predicted.
* It will not settle what the section's words leave open. The effect of a
  report filed around the s.187(3) expiry turns on case law, which comes back
  as retrieved passages for the advocate to read, not as a finding here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

from app.models.enums import OffenceGravity
from app.services.advocate_provisions import PROVISIONS, provision_sources
from app.services.investigation_timeline import (
    InvestigationFacts,
    add_calendar_months,
    investigation_deadlines,
)
from app.services.section_mapping import map_sections

# The BNSS came into force on this date; the same date the authority check and
# the concordance use for the repeal of the CrPC.
BNSS_COMMENCEMENT = date(2024, 7, 1)
TEN_YEARS_MONTHS = 120
SEVEN_YEARS_MONTHS = 84


class BailRoute(StrEnum):
    REGULAR = "regular"
    ANTICIPATORY = "anticipatory"
    DEFAULT = "default"
    UNDERTRIAL = "undertrial"


class RouteStatus(StrEnum):
    # The section says "shall" on the facts entered. Not a prediction.
    ENTITLED_ON_TEXT = "entitled_on_text"
    # The section says "may": a discretion, and nothing computes how it runs.
    DISCRETIONARY = "discretionary"
    BARRED_ON_TEXT = "barred_on_text"
    NOT_YET = "not_yet"
    # Dates are known, but the text alone does not resolve the effect.
    NEEDS_REVIEW = "needs_review"
    UNDETERMINED = "undetermined"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class BailFacts:
    as_of: date
    classification: str = "unknown"  # bailable | non_bailable | unknown
    gravity: OffenceGravity = OffenceGravity.UNKNOWN
    punishable_with_death_or_life: bool | None = None
    max_punishment_months: int | None = None
    information_recorded_on: date | None = None
    arrested_on: date | None = None
    first_remand_on: date | None = None
    report_filed: bool | None = None
    report_filed_on: date | None = None
    in_custody: bool | None = None
    custody_started_on: date | None = None
    custody_days_before_current_spell: int = 0
    delay_by_accused_days: int = 0
    first_time_offender: bool | None = None
    other_cases_pending: bool | None = None
    previous_conviction_bar: bool | None = None
    child_woman_sick_or_infirm: bool | None = None
    involves_bns_65_or_70_2: bool | None = None
    triable_by_magistrate: bool | None = None
    first_evidence_date: date | None = None
    in_custody_whole_trial_period: bool | None = None


@dataclass
class RouteFinding:
    route: BailRoute
    label: str
    status: RouteStatus
    headline: str
    provisions: list[str]
    forum: str = ""
    dates: list[dict[str, Any]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "route": self.route.value,
            "label": self.label,
            "status": self.status.value,
            "headline": self.headline,
            "forum": self.forum,
            "dates": self.dates,
            "missing": self.missing,
            "cautions": self.cautions,
            "sources": provision_sources(*self.provisions),
        }


def _midnight(value: date | None) -> datetime | None:
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc) if value else None


def _long(value: date) -> str:
    return f"{value.day} {value.strftime('%B %Y')}"


def _date_row(label: str, value: date, *, computed_from: str, provision: str, as_of: date) -> dict[str, Any]:
    return {
        "label": label,
        "date": value.isoformat(),
        "computed_from": computed_from,
        "provision": provision,
        "state": "passed" if as_of > value else "today" if as_of == value else "upcoming",
    }


def resolved_gravity(facts: BailFacts) -> OffenceGravity:
    """The s.187(3) distinction, from what was entered and nothing else."""
    if facts.gravity is not OffenceGravity.UNKNOWN:
        return facts.gravity
    if facts.punishable_with_death_or_life:
        return OffenceGravity.DEATH_LIFE_OR_TEN_YEARS_OR_MORE
    if facts.max_punishment_months is not None:
        return (
            OffenceGravity.DEATH_LIFE_OR_TEN_YEARS_OR_MORE
            if facts.max_punishment_months >= TEN_YEARS_MONTHS
            else OffenceGravity.OTHER
        )
    return OffenceGravity.UNKNOWN


def _regular(facts: BailFacts) -> RouteFinding:
    label = "Regular bail"
    if facts.classification == "bailable":
        return RouteFinding(
            BailRoute.REGULAR, label, RouteStatus.ENTITLED_ON_TEXT,
            "Entered as bailable. s.478(1) reads that such a person, prepared to give bail, "
            '"shall be released on bail".',
            ["bnss_478_1"],
            forum="The officer in charge of the police station, or the Court",
        )
    if facts.classification != "non_bailable":
        return RouteFinding(
            BailRoute.REGULAR, label, RouteStatus.UNDETERMINED,
            "Not assessed: whether the offence is bailable is not recorded. Check the First "
            "Schedule to the BNSS, or the special Act, and enter it. This tool does not infer it "
            "from the name of the offence.",
            ["bnss_478_1", "bnss_480_1"],
            missing=["whether the offence is bailable or non-bailable"],
        )

    finding = RouteFinding(
        BailRoute.REGULAR, label, RouteStatus.DISCRETIONARY,
        'Non-bailable. s.480(1) reads that the person "may be released on bail": a discretion, '
        "subject to the restrictions below.",
        ["bnss_480_1"],
        forum="A Court other than the High Court or Court of Session under s.480; the High Court "
        "or Court of Session under s.483",
    )
    finding.provisions.append("bnss_483_1")
    bars: list[str] = []
    if facts.punishable_with_death_or_life:
        bars.append("s.480(1)(i) restricts release where reasonable grounds appear to believe guilt of an offence punishable with death or life imprisonment")
        finding.provisions.append("bnss_480_1_i")
    elif facts.punishable_with_death_or_life is None:
        finding.missing.append("whether the offence is punishable with death or life imprisonment")
    if facts.previous_conviction_bar:
        bars.append("s.480(1)(ii) restricts release on the previous convictions you entered")
        finding.provisions.append("bnss_480_1_ii")
    elif facts.previous_conviction_bar is None:
        finding.missing.append("previous convictions of the kind s.480(1)(ii) describes")
    if bars:
        if facts.child_woman_sick_or_infirm:
            finding.provisions.append("bnss_480_child_woman")
            finding.status = RouteStatus.DISCRETIONARY
            finding.headline = (
                "s.480(1) restrictions engage on these facts, and the first proviso lets the "
                "Court direct release of a child, woman, or sick or infirm person."
            )
        else:
            finding.status = RouteStatus.BARRED_ON_TEXT
            finding.headline = (
                "Before a Magistrate, the restrictions in s.480(1) engage on the facts entered. "
                "s.483 before the High Court or Court of Session is framed separately."
            )
        finding.cautions.extend(bars)
    months = facts.max_punishment_months
    if facts.punishable_with_death_or_life or (months is not None and months >= SEVEN_YEARS_MONTHS):
        finding.provisions.extend(["bnss_480_prosecutor", "bnss_480_3", "bnss_483_notice"])
        finding.cautions.append(
            "On the punishment entered, the fourth proviso to s.480(1) requires an opportunity of "
            "hearing to the Public Prosecutor, and s.480(3) conditions apply."
        )
    if facts.triable_by_magistrate and facts.first_evidence_date:
        due = facts.first_evidence_date + timedelta(days=60)
        finding.dates.append(
            _date_row(
                "Sixty days from the first date fixed for evidence", due,
                computed_from=f"first date fixed for evidence, {_long(facts.first_evidence_date)}",
                provision="BNSS s.480(6)", as_of=facts.as_of,
            )
        )
        finding.provisions.append("bnss_480_6")
        if facts.as_of > due and facts.in_custody_whole_trial_period:
            finding.cautions.append(
                "s.480(6): if the trial has not concluded, the sub-section reads that the person "
                '"shall" be released unless the Magistrate records reasons otherwise.'
            )
        elif facts.in_custody_whole_trial_period is None:
            finding.missing.append("whether the accused was in custody for the whole of the s.480(6) period")
    return finding


def _anticipatory(facts: BailFacts) -> RouteFinding:
    label = "Anticipatory bail"
    forum = "The High Court or the Court of Session"
    if facts.involves_bns_65_or_70_2:
        return RouteFinding(
            BailRoute.ANTICIPATORY, label, RouteStatus.BARRED_ON_TEXT,
            "s.482(4) excludes this section where the accusation is under BNS s.65 or s.70(2), "
            "as you entered.",
            ["bnss_482_4"], forum=forum,
        )
    if facts.in_custody:
        return RouteFinding(
            BailRoute.ANTICIPATORY, label, RouteStatus.NOT_APPLICABLE,
            "Entered as already in custody. s.482(1) speaks of a person who has reason to believe "
            "he may be arrested. Look at regular bail instead.",
            ["bnss_482_1"], forum=forum,
        )
    if facts.classification == "bailable":
        return RouteFinding(
            BailRoute.ANTICIPATORY, label, RouteStatus.NOT_APPLICABLE,
            "Entered as bailable. s.482(1) speaks of an accusation of a non-bailable offence.",
            ["bnss_482_1", "bnss_478_1"], forum=forum,
        )
    finding = RouteFinding(
        BailRoute.ANTICIPATORY, label, RouteStatus.DISCRETIONARY,
        'The Court "may, if it thinks fit" direct release on bail in the event of arrest, and may '
        "attach the s.482(2) conditions.",
        ["bnss_482_1", "bnss_482_2"], forum=forum,
    )
    if facts.classification != "non_bailable":
        finding.missing.append("whether the offence is bailable or non-bailable")
    if facts.involves_bns_65_or_70_2 is None:
        finding.missing.append("whether the accusation is under BNS s.65 or s.70(2), which s.482(4) excludes")
        finding.provisions.append("bnss_482_4")
    if facts.in_custody is None:
        finding.missing.append("whether the applicant is already in custody")
    return finding


def _default(facts: BailFacts) -> RouteFinding:
    label = "Default bail"
    forum = "The Magistrate"
    gravity = resolved_gravity(facts)
    # The same computation the police timeline shows, so the two cannot disagree.
    deadline = next(
        (
            item
            for item in investigation_deadlines(
                InvestigationFacts(
                    arrested_at=_midnight(facts.arrested_on),
                    first_remand_at=_midnight(facts.first_remand_on),
                    gravity=gravity,
                )
            )
            if item.key == "default_bail_entitlement"
        ),
        None,
    )
    provisions = ["bnss_187_3", "bnss_187_3_i", "bnss_187_3_ii", "bnss_187_3_release"]
    if deadline is None:
        return RouteFinding(
            BailRoute.DEFAULT, label, RouteStatus.UNDETERMINED,
            "Not computed: no arrest or remand date is recorded.",
            provisions, forum=forum,
            missing=["the date of first remand"],
        )
    if deadline.due_at is None:
        return RouteFinding(
            BailRoute.DEFAULT, label, RouteStatus.UNDETERMINED,
            f"Not computed: {deadline.undetermined_because}.",
            provisions, forum=forum,
            missing=[deadline.undetermined_because],
        )
    due = deadline.due_at.date()
    days = 90 if gravity is OffenceGravity.DEATH_LIFE_OR_TEN_YEARS_OR_MORE else 60
    finding = RouteFinding(
        BailRoute.DEFAULT, label, RouteStatus.NOT_YET, "", provisions, forum=forum,
        dates=[
            _date_row(
                f"{days}-day period ends", due,
                computed_from=f"{days} days from first remand on {_long(facts.first_remand_on)}",  # type: ignore[arg-type]
                provision=deadline.provision, as_of=facts.as_of,
            )
        ],
        cautions=[
            "The date is first remand plus the period. How the days are counted, and any longer "
            "period under a special Act, are not computed here.",
        ],
    )
    filed_on = facts.report_filed_on
    if facts.report_filed and filed_on is None:
        finding.status = RouteStatus.NEEDS_REVIEW
        finding.headline = (
            f"The computed period ends on {_long(due)}, and a report is recorded as filed with no "
            "date. Enter the date to place it against the period."
        )
        finding.missing.append("the date the police report was filed")
    elif filed_on is not None:
        finding.status = RouteStatus.NEEDS_REVIEW
        relation = "within" if filed_on <= due else "after"
        finding.headline = (
            f"The computed period ends on {_long(due)}. A report is recorded as filed on "
            f"{_long(filed_on)}, {relation} that period. s.187(3) does not itself state the effect "
            "of a filed report: read the retrieved authorities and check when any application was made."
        )
    elif facts.report_filed is None:
        finding.status = RouteStatus.NEEDS_REVIEW if facts.as_of > due else RouteStatus.NOT_YET
        finding.missing.append("whether a police report has been filed")
        finding.headline = (
            f"The computed period {'ended' if facts.as_of > due else 'ends'} on {_long(due)}. "
            "Whether a report has been filed is not recorded, and the assessment depends on it."
        )
    elif facts.as_of > due:
        finding.status = RouteStatus.ENTITLED_ON_TEXT
        finding.headline = (
            f"The period ended on {_long(due)} and no report is recorded. s.187(3) reads that the "
            'accused "shall be released on bail if he is prepared to and does furnish bail".'
        )
        finding.provisions.append("bnss_187_expl_1")
    else:
        finding.status = RouteStatus.NOT_YET
        finding.headline = (
            f"The period ends on {_long(due)}, {(due - facts.as_of).days} day(s) from the date assessed."
        )
    return finding


def _add_fraction(start: date, months: int, divisor: int) -> date:
    """A fraction of a maximum sentence, as calendar months plus remaining days.

    A seven-year maximum gives forty-two months at one-half exactly, but five
    years at one-third leaves no whole number of months, so the remainder is
    carried as thirtieths of a month.
    """
    whole, remainder = divmod(months, divisor)
    return add_calendar_months(start, whole) + timedelta(days=round(remainder * 30 / divisor))


def _undertrial(facts: BailFacts) -> RouteFinding:
    label = "Undertrial release (s.479)"
    forum = "The Court. The Superintendent of the jail must apply under s.479(3)."
    base = ["bnss_479_1", "bnss_479_explanation"]
    if facts.punishable_with_death_or_life:
        return RouteFinding(
            BailRoute.UNDERTRIAL, label, RouteStatus.BARRED_ON_TEXT,
            "s.479(1) does not extend to an offence for which death or life imprisonment is "
            "specified as one of the punishments, as you entered.",
            ["bnss_479_1"], forum=forum,
        )
    missing = []
    if facts.punishable_with_death_or_life is None:
        missing.append("whether death or life imprisonment is specified for the offence")
    if facts.max_punishment_months is None:
        missing.append("the maximum punishment specified for the offence")
    if facts.custody_started_on is None:
        missing.append("the date detention began")
    if facts.max_punishment_months is None or facts.custody_started_on is None:
        return RouteFinding(
            BailRoute.UNDERTRIAL, label, RouteStatus.UNDETERMINED,
            "Not computed: the fractions in s.479(1) need the maximum punishment and the date "
            "detention began.",
            base, forum=forum, missing=missing,
        )

    credit = facts.delay_by_accused_days - facts.custody_days_before_current_spell
    start = facts.custody_started_on + timedelta(days=credit)
    months = facts.max_punishment_months
    half = _add_fraction(start, months, 2)
    third = _add_fraction(start, months, 3)
    maximum = add_calendar_months(start, months)
    basis = (
        f"detention from {_long(facts.custody_started_on)}"
        + (f", less {facts.custody_days_before_current_spell} day(s) of earlier detention" if facts.custody_days_before_current_spell else "")
        + (f", plus {facts.delay_by_accused_days} day(s) excluded as delay caused by the accused" if facts.delay_by_accused_days else "")
    )
    dates = [
        _date_row("One-half of the maximum", half, computed_from=basis, provision="BNSS s.479(1)", as_of=facts.as_of),
        _date_row("One-third of the maximum (first-time offender)", third, computed_from=basis, provision="BNSS s.479(1), first proviso", as_of=facts.as_of),
        _date_row("The whole of the maximum", maximum, computed_from=basis, provision="BNSS s.479(1), third proviso", as_of=facts.as_of),
    ]
    finding = RouteFinding(
        BailRoute.UNDERTRIAL, label, RouteStatus.NOT_YET, "",
        [*base, "bnss_479_first_time", "bnss_479_continued", "bnss_479_maximum", "bnss_479_2", "bnss_479_3"],
        forum=forum, dates=dates, missing=missing,
        cautions=[
            "The second proviso lets the Court, after hearing the Public Prosecutor and for "
            "recorded reasons, order continued detention beyond one-half.",
            "Delay caused by the accused is taken as you entered it; the Court decides what counts.",
        ],
    )
    if facts.as_of > maximum:
        finding.status = RouteStatus.ENTITLED_ON_TEXT
        finding.headline = (
            f"Detention has passed the whole of the maximum on {_long(maximum)}. The third proviso "
            'reads that no such person "shall in any case be detained" beyond it.'
        )
        return finding
    if facts.other_cases_pending:
        finding.status = RouteStatus.BARRED_ON_TEXT
        finding.headline = (
            "Entered as having more than one offence or case pending. s.479(2) reads that he "
            '"shall not be released on bail by the Court", subject to the third proviso: '
            f"the whole of the maximum falls on {_long(maximum)}."
        )
        return finding
    if facts.other_cases_pending is None:
        finding.missing.append("whether another offence or case is pending, which s.479(2) turns on")
    if facts.first_time_offender is None:
        finding.missing.append("whether this is a first-time offender, which decides between one-third and one-half")
        reached = facts.as_of > half
        finding.status = RouteStatus.ENTITLED_ON_TEXT if reached else RouteStatus.UNDETERMINED
        finding.headline = (
            f"One-half fell on {_long(half)}, so that threshold is passed on either answer. "
            if reached else
            f"One-third falls on {_long(third)} and one-half on {_long(half)}. Which applies depends on "
            "whether this is a first-time offender."
        )
        return finding
    threshold, words, what = (
        (third, "one-third", "released on bond") if facts.first_time_offender
        else (half, "one-half", "released by the Court on bail")
    )
    if facts.as_of > threshold:
        finding.status = RouteStatus.ENTITLED_ON_TEXT
        finding.headline = (
            f"Detention passed {words} of the maximum on {_long(threshold)}. s.479(1) reads that he "
            f'"shall be {what}", subject to the second proviso.'
        )
    else:
        finding.headline = (
            f"{words.capitalize()} of the maximum falls on {_long(threshold)}, "
            f"{(threshold - facts.as_of).days} day(s) from the date assessed."
        )
    return finding


_ROUTES = {
    BailRoute.REGULAR: _regular,
    BailRoute.ANTICIPATORY: _anticipatory,
    BailRoute.DEFAULT: _default,
    BailRoute.UNDERTRIAL: _undertrial,
}

# Which CrPC provision each route's BNSS section replaced, per the concordance.
_CONCORDANCE_ROUTE_SECTION = {
    BailRoute.REGULAR: "480",
    BailRoute.ANTICIPATORY: "482",
    BailRoute.DEFAULT: "187",
    BailRoute.UNDERTRIAL: "479",
}


def _pre_bnss_notice(facts: BailFacts, routes: list[BailRoute]) -> dict[str, Any] | None:
    """Pending proceedings may still run under the repealed Code.

    Said only when a date entered falls before commencement. The computed
    dates above read the BNSS text, and the old provisions are not the same.
    """
    entered = [d for d in (facts.information_recorded_on, facts.arrested_on, facts.first_remand_on) if d]
    if not entered or min(entered) >= BNSS_COMMENCEMENT:
        return None
    counterparts = []
    for route in routes:
        for mapping in map_sections("BNSS", _CONCORDANCE_ROUTE_SECTION[route]):
            counterparts.append(
                {
                    "route": route.value,
                    "repealed_provision": f"{mapping.to_code} s.{mapping.to_section}",
                    "bnss_provision": f"BNSS s.{mapping.from_section}",
                    "elements_changed": mapping.ingredients_changed,
                }
            )
    return {
        "text": (
            f"A date you entered falls before {_long(BNSS_COMMENCEMENT)}, when the CrPC was repealed. "
            "s.531(2)(a) continues matters pending before that date under the old Code, so the "
            "BNSS findings on this page may not govern. They are not recomputed under the repealed "
            "provisions listed."
        ),
        "sources": provision_sources("bnss_531_2_a"),
        "counterparts": counterparts,
    }


def assess_bail(facts: BailFacts, routes: list[BailRoute] | None = None) -> dict[str, Any]:
    chosen = routes or list(BailRoute)
    findings = [_ROUTES[route](facts) for route in chosen]
    return {
        "as_of": facts.as_of.isoformat(),
        "routes": [finding.as_dict() for finding in findings],
        "pre_bnss_notice": _pre_bnss_notice(facts, chosen),
        "method": (
            "Computed from the dates and facts you entered and the text of the BNSS, with no model "
            "involved. A finding reports what the section's words say on those facts. It does not "
            "say what a court will do."
        ),
    }


def retrieval_query(facts_text: str | None, routes: list[BailRoute]) -> str:
    """What to look for in the judgments held, for the routes being assessed."""
    terms = {
        BailRoute.REGULAR: "bail non-bailable offence grant of bail considerations",
        BailRoute.ANTICIPATORY: "anticipatory bail apprehension of arrest",
        BailRoute.DEFAULT: "default bail expiry of period report not filed",
        BailRoute.UNDERTRIAL: "undertrial detention maximum period release",
    }
    return " ".join([facts_text or "", *(terms[route] for route in routes)])[:2000].strip()


__all__ = ["BailFacts", "BailRoute", "RouteStatus", "assess_bail", "resolved_gravity", "retrieval_query", "PROVISIONS"]
