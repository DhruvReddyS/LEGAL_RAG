"""Deadline arithmetic, tested where getting it wrong costs liberty.

These are not arithmetic exercises. Each case below is a way the
calculation could be plausibly wrong and still look right in an answer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.investigation_timeline import (
    Deadline,
    InvestigationFacts,
    OffenceGravity,
    add_calendar_months,
    breached,
    investigation_deadlines,
    undetermined,
)

IST = timezone(timedelta(hours=5, minutes=30))


def _at(year: int, month: int, day: int, hour: int = 10) -> datetime:
    return datetime(year, month, day, hour, tzinfo=IST)


def _by_key(facts: InvestigationFacts) -> dict[str, Deadline]:
    return {d.key: d for d in investigation_deadlines(facts)}


class TestTheDefaultBailPeriodRunsFromFirstRemand:
    """The classic error, and the reason this module exists.

    The s.187(3) period runs from the first remand, not the arrest. An
    accused arrested on the 1st and first remanded on the 3rd has a period
    expiring two days later than an arrest-based calculation would show --
    and an investigating officer who files on the strength of the wrong
    date has already handed over an indefeasible entitlement to bail.
    """

    def test_ninety_days_run_from_the_remand_not_the_arrest(self) -> None:
        facts = InvestigationFacts(
            arrested_at=_at(2026, 1, 1),
            first_remand_at=_at(2026, 1, 3),
            gravity=OffenceGravity.DEATH_LIFE_OR_TEN_YEARS_OR_MORE,
        )

        deadline = _by_key(facts)["default_bail_entitlement"]

        assert deadline.due_at == _at(2026, 1, 3) + timedelta(days=90)
        assert deadline.due_at != _at(2026, 1, 1) + timedelta(days=90)

    def test_sixty_days_for_any_other_offence(self) -> None:
        facts = InvestigationFacts(
            arrested_at=_at(2026, 1, 1),
            first_remand_at=_at(2026, 1, 3),
            gravity=OffenceGravity.OTHER,
        )

        deadline = _by_key(facts)["default_bail_entitlement"]

        assert deadline.due_at == _at(2026, 1, 3) + timedelta(days=60)
        assert "187(3)(ii)" in deadline.provision

    def test_without_a_remand_date_it_refuses_rather_than_using_the_arrest(self) -> None:
        facts = InvestigationFacts(
            arrested_at=_at(2026, 1, 1),
            gravity=OffenceGravity.OTHER,
        )

        deadline = _by_key(facts)["default_bail_entitlement"]

        assert deadline.due_at is None
        assert "first remand" in deadline.undetermined_because


class TestUnknownGravityFailsClosed:
    def test_it_does_not_assume_the_shorter_or_the_longer_period(self) -> None:
        """Assuming sixty days flatters compliance; assuming ninety hides
        an entitlement that has already accrued. Neither is acceptable, so
        the deadline is returned undetermined and says why."""
        facts = InvestigationFacts(
            first_remand_at=_at(2026, 1, 3), gravity=OffenceGravity.UNKNOWN
        )

        deadline = _by_key(facts)["default_bail_entitlement"]

        assert deadline.due_at is None
        assert "gravity" in deadline.undetermined_because

    def test_the_obligation_is_still_listed(self) -> None:
        """Dropping it would read as "no default-bail deadline applies".

        The obligation exists on these facts; only its date is unknown, and
        an omitted row and an inapplicable rule are indistinguishable to
        whoever reads the output.
        """
        facts = InvestigationFacts(
            first_remand_at=_at(2026, 1, 3), gravity=OffenceGravity.UNKNOWN
        )

        assert "default_bail_entitlement" in _by_key(facts)

    def test_an_undetermined_deadline_is_not_reported_as_compliant(self) -> None:
        facts = InvestigationFacts(
            first_remand_at=_at(2026, 1, 3), gravity=OffenceGravity.UNKNOWN
        )
        deadline = _by_key(facts)["default_bail_entitlement"]

        # Not False. False would assert compliance that was never established.
        assert deadline.is_breached(_at(2030, 1, 1)) is None
        assert deadline not in breached(investigation_deadlines(facts), _at(2030, 1, 1))
        assert deadline in undetermined(investigation_deadlines(facts))


class TestTwoMonthsIsNotSixtyDays:
    """s.193(2) says two months. The difference is up to two days, which is
    the difference between a completed investigation and a breach."""

    def test_two_months_from_the_first_of_january(self) -> None:
        facts = InvestigationFacts(
            information_recorded_at=_at(2026, 1, 1), is_listed_sexual_offence=True
        )

        due = _by_key(facts)["investigation_completion"].due_at

        assert due == _at(2026, 3, 1)
        assert due != _at(2026, 1, 1) + timedelta(days=60)

    @pytest.mark.parametrize(
        ("start", "expected"),
        [
            ((2025, 12, 31), (2026, 2, 28)),
            ((2027, 12, 31), (2028, 2, 29)),
            ((2026, 1, 31), (2026, 3, 31)),
            ((2026, 8, 31), (2026, 10, 31)),
        ],
    )
    def test_a_short_target_month_clamps_instead_of_overflowing(
        self, start: tuple[int, int, int], expected: tuple[int, int, int]
    ) -> None:
        """31 December plus two months is not 31 February.

        The leap-year row is included because 2028 is one and the clamp has
        to land on the 29th, not the 28th.
        """
        assert add_calendar_months(_at(*start), 2) == _at(*expected)

    def test_the_year_rolls_over(self) -> None:
        assert add_calendar_months(_at(2026, 11, 15), 2) == _at(2027, 1, 15)


class TestTwentyFourHourPeriods:
    def test_production_is_marked_as_the_earliest_the_period_could_expire(self) -> None:
        """s.58 excludes the journey from the place of arrest.

        The module cannot know the journey time, so presenting the computed
        moment as the limit would overstate how long the officer has -- and
        an officer relying on it would be late.
        """
        facts = InvestigationFacts(arrested_at=_at(2026, 1, 1, 14))

        deadline = _by_key(facts)["production_before_magistrate"]

        assert deadline.due_at == _at(2026, 1, 2, 14)
        assert deadline.is_earliest_possible

    def test_the_default_bail_period_is_not_marked_as_approximate(self) -> None:
        """It is an exact period, and marking it approximate would invite
        treating a hard entitlement as a soft one."""
        facts = InvestigationFacts(
            first_remand_at=_at(2026, 1, 3), gravity=OffenceGravity.OTHER
        )

        assert not _by_key(facts)["default_bail_entitlement"].is_earliest_possible


class TestOnlyApplicableObligationsAppear:
    def test_an_ordinary_offence_gets_no_sexual_offence_deadlines(self) -> None:
        facts = InvestigationFacts(
            information_recorded_at=_at(2026, 1, 1), is_listed_sexual_offence=False
        )

        keys = _by_key(facts)

        assert "investigation_completion" not in keys
        assert "victim_medical_examination" not in keys
        assert "victim_progress_update" in keys

    def test_no_death_means_no_inquest_deadlines(self) -> None:
        facts = InvestigationFacts(information_recorded_at=_at(2026, 1, 1))

        keys = _by_key(facts)

        assert "post_mortem_referral" not in keys
        assert "inquest_report_to_magistrate" not in keys

    def test_an_unnatural_death_gets_both_twenty_four_hour_obligations(self) -> None:
        facts = InvestigationFacts(
            is_unnatural_death=True, death_occurred_at=_at(2026, 1, 1, 6)
        )

        keys = _by_key(facts)

        assert keys["post_mortem_referral"].due_at == _at(2026, 1, 2, 6)
        assert keys["inquest_report_to_magistrate"].due_at == _at(2026, 1, 2, 6)

    def test_empty_facts_produce_no_deadlines_rather_than_guesses(self) -> None:
        assert investigation_deadlines(InvestigationFacts()) == []


class TestEveryDeadlineCitesItsProvision:
    def test_no_deadline_is_returned_without_the_section_it_comes_from(self) -> None:
        """An uncheckable deadline is worse than none.

        The whole output is only usable because each row can be taken back
        to the Act; a row without a citation asks to be believed.
        """
        facts = InvestigationFacts(
            information_recorded_at=_at(2026, 1, 1),
            arrested_at=_at(2026, 1, 1),
            first_remand_at=_at(2026, 1, 3),
            accused_produced_at=_at(2026, 1, 3),
            death_occurred_at=_at(2026, 1, 1),
            gravity=OffenceGravity.OTHER,
            is_listed_sexual_offence=True,
            preliminary_enquiry_started_at=_at(2026, 1, 1),
            is_unnatural_death=True,
        )

        deadlines = investigation_deadlines(facts)

        assert len(deadlines) == 9
        for deadline in deadlines:
            assert deadline.provision.startswith("BNSS s."), deadline.key
            assert deadline.obligation.strip()
            assert deadline.consequence.strip()


class TestBreachDetection:
    def test_a_passed_deadline_is_breached(self) -> None:
        facts = InvestigationFacts(arrested_at=_at(2026, 1, 1))
        deadlines = investigation_deadlines(facts)

        assert [d.key for d in breached(deadlines, _at(2026, 1, 3))] == [
            "production_before_magistrate"
        ]

    def test_a_future_deadline_is_not_breached(self) -> None:
        facts = InvestigationFacts(arrested_at=_at(2026, 1, 1))

        assert breached(investigation_deadlines(facts), _at(2026, 1, 1, 20)) == []

    def test_remaining_time_is_signed(self) -> None:
        facts = InvestigationFacts(arrested_at=_at(2026, 1, 1, 10))
        deadline = _by_key(facts)["production_before_magistrate"]

        assert deadline.remaining(_at(2026, 1, 2, 4)) == timedelta(hours=6)
        assert deadline.remaining(_at(2026, 1, 3, 10)) == timedelta(hours=-24)
