"""Bail routes: what the text says on the facts entered, and nothing further."""

from __future__ import annotations

from datetime import date

import pytest

from app.models.enums import OffenceGravity
from app.services.bail import BailFacts, BailRoute, RouteStatus, assess_bail
from app.services.investigation_timeline import InvestigationFacts, investigation_deadlines
from datetime import datetime, timezone

TODAY = date(2026, 11, 4)


def route(facts: BailFacts, which: BailRoute) -> dict:
    return assess_bail(facts, [which])["routes"][0]


class TestDefaultBail:
    def test_it_runs_from_first_remand_not_from_arrest(self):
        result = route(
            BailFacts(
                as_of=TODAY, gravity=OffenceGravity.OTHER, report_filed=False,
                arrested_on=date(2026, 1, 1), first_remand_on=date(2026, 1, 11),
            ),
            BailRoute.DEFAULT,
        )
        assert result["dates"][0]["date"] == "2026-03-12"  # 60 days from 11 Jan, not 1 Jan

    def test_the_date_matches_the_police_timeline_exactly(self):
        remand = date(2026, 2, 1)
        result = route(
            BailFacts(as_of=TODAY, gravity=OffenceGravity.DEATH_LIFE_OR_TEN_YEARS_OR_MORE, report_filed=False, first_remand_on=remand),
            BailRoute.DEFAULT,
        )
        police = next(
            item for item in investigation_deadlines(
                InvestigationFacts(
                    first_remand_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
                    gravity=OffenceGravity.DEATH_LIFE_OR_TEN_YEARS_OR_MORE,
                )
            ) if item.key == "default_bail_entitlement"
        )
        assert result["dates"][0]["date"] == police.due_at.date().isoformat()

    def test_unknown_gravity_is_a_stated_unknown_not_sixty_days(self):
        result = route(BailFacts(as_of=TODAY, first_remand_on=date(2026, 1, 1)), BailRoute.DEFAULT)
        assert result["status"] == RouteStatus.UNDETERMINED
        assert result["dates"] == []
        assert "ninety or sixty" in result["missing"][0]

    def test_gravity_follows_the_punishment_entered(self):
        ten_years = BailFacts(as_of=TODAY, max_punishment_months=120, first_remand_on=date(2026, 1, 1), report_filed=False)
        seven_years = BailFacts(as_of=TODAY, max_punishment_months=84, first_remand_on=date(2026, 1, 1), report_filed=False)
        assert route(ten_years, BailRoute.DEFAULT)["dates"][0]["date"] == "2026-04-01"
        assert route(seven_years, BailRoute.DEFAULT)["dates"][0]["date"] == "2026-03-02"

    def test_on_the_last_day_the_period_has_not_expired(self):
        result = route(
            BailFacts(as_of=date(2026, 3, 2), gravity=OffenceGravity.OTHER, first_remand_on=date(2026, 1, 1), report_filed=False),
            BailRoute.DEFAULT,
        )
        assert result["status"] == RouteStatus.NOT_YET

    def test_after_expiry_with_no_report_it_reads_the_section(self):
        result = route(
            BailFacts(as_of=date(2026, 3, 3), gravity=OffenceGravity.OTHER, first_remand_on=date(2026, 1, 1), report_filed=False),
            BailRoute.DEFAULT,
        )
        assert result["status"] == RouteStatus.ENTITLED_ON_TEXT
        assert "shall be released on bail" in result["headline"]

    @pytest.mark.parametrize("filed", [date(2026, 2, 1), date(2026, 4, 1)])
    def test_a_filed_report_is_left_to_case_law_either_side_of_expiry(self, filed):
        """The section's text does not state this; a finding here would be from memory."""
        result = route(
            BailFacts(as_of=TODAY, gravity=OffenceGravity.OTHER, first_remand_on=date(2026, 1, 1), report_filed=True, report_filed_on=filed),
            BailRoute.DEFAULT,
        )
        assert result["status"] == RouteStatus.NEEDS_REVIEW
        assert "retrieved authorities" in result["headline"]

    def test_no_answer_on_the_report_is_not_treated_as_no_report(self):
        result = route(
            BailFacts(as_of=TODAY, gravity=OffenceGravity.OTHER, first_remand_on=date(2026, 1, 1)),
            BailRoute.DEFAULT,
        )
        assert result["status"] == RouteStatus.NEEDS_REVIEW
        assert any("police report" in item for item in result["missing"])


class TestUndertrial:
    def base(self, **changes) -> BailFacts:
        values = dict(
            as_of=TODAY, punishable_with_death_or_life=False, max_punishment_months=84,
            custody_started_on=date(2023, 1, 1), first_time_offender=False, other_cases_pending=False,
        )
        return BailFacts(**{**values, **changes})

    def test_fractions_of_a_seven_year_maximum(self):
        dates = {row["label"]: row["date"] for row in route(self.base(), BailRoute.UNDERTRIAL)["dates"]}
        assert dates["One-half of the maximum"] == "2026-07-01"
        assert dates["One-third of the maximum (first-time offender)"] == "2025-05-01"
        assert dates["The whole of the maximum"] == "2030-01-01"

    def test_a_first_offender_is_measured_at_one_third(self):
        facts = self.base(as_of=date(2025, 6, 1), first_time_offender=True)
        result = route(facts, BailRoute.UNDERTRIAL)
        assert result["status"] == RouteStatus.ENTITLED_ON_TEXT
        assert "released on bond" in result["headline"]
        assert route(self.base(as_of=date(2025, 6, 1)), BailRoute.UNDERTRIAL)["status"] == RouteStatus.NOT_YET

    def test_death_or_life_is_outside_the_section(self):
        result = route(self.base(punishable_with_death_or_life=True), BailRoute.UNDERTRIAL)
        assert result["status"] == RouteStatus.BARRED_ON_TEXT
        assert result["dates"] == []

    def test_multiple_cases_bar_it_until_the_whole_maximum(self):
        barred = route(self.base(other_cases_pending=True), BailRoute.UNDERTRIAL)
        assert barred["status"] == RouteStatus.BARRED_ON_TEXT
        past = route(self.base(other_cases_pending=True, as_of=date(2030, 1, 2)), BailRoute.UNDERTRIAL)
        assert past["status"] == RouteStatus.ENTITLED_ON_TEXT

    def test_delay_by_the_accused_pushes_the_date_back(self):
        dates = route(self.base(delay_by_accused_days=31), BailRoute.UNDERTRIAL)["dates"]
        assert dates[0]["date"] == "2026-08-01"

    def test_earlier_detention_brings_the_date_forward(self):
        dates = route(self.base(custody_days_before_current_spell=31), BailRoute.UNDERTRIAL)["dates"]
        assert dates[0]["date"] == "2026-06-01"

    def test_missing_maximum_gives_no_dates(self):
        result = route(self.base(max_punishment_months=None), BailRoute.UNDERTRIAL)
        assert result["status"] == RouteStatus.UNDETERMINED and result["dates"] == []

    def test_unknown_first_offender_status_does_not_assume_either(self):
        result = route(self.base(first_time_offender=None, as_of=date(2025, 6, 1)), BailRoute.UNDERTRIAL)
        assert result["status"] == RouteStatus.UNDETERMINED
        assert any("first-time" in item for item in result["missing"])


class TestRegularAndAnticipatory:
    def test_classification_is_never_inferred(self):
        result = route(BailFacts(as_of=TODAY), BailRoute.REGULAR)
        assert result["status"] == RouteStatus.UNDETERMINED

    def test_bailable_reads_shall(self):
        result = route(BailFacts(as_of=TODAY, classification="bailable"), BailRoute.REGULAR)
        assert result["status"] == RouteStatus.ENTITLED_ON_TEXT
        assert "shall be released on bail" in result["sources"][0]["excerpt"]

    def test_non_bailable_is_discretionary_not_favourable(self):
        result = route(
            BailFacts(as_of=TODAY, classification="non_bailable", punishable_with_death_or_life=False, previous_conviction_bar=False),
            BailRoute.REGULAR,
        )
        assert result["status"] == RouteStatus.DISCRETIONARY

    def test_the_magistrate_restriction_engages_and_names_itself(self):
        result = route(
            BailFacts(as_of=TODAY, classification="non_bailable", punishable_with_death_or_life=True),
            BailRoute.REGULAR,
        )
        assert result["status"] == RouteStatus.BARRED_ON_TEXT
        assert any(item["section"] == "BNSS s.480(1)(i)" for item in result["sources"])
        assert any(item["section"] == "BNSS s.483(1), first proviso" for item in result["sources"])

    def test_the_child_woman_sick_or_infirm_proviso_is_read(self):
        result = route(
            BailFacts(as_of=TODAY, classification="non_bailable", punishable_with_death_or_life=True, child_woman_sick_or_infirm=True),
            BailRoute.REGULAR,
        )
        assert result["status"] == RouteStatus.DISCRETIONARY

    def test_s_480_6_sixty_days_is_computed_from_the_evidence_date(self):
        result = route(
            BailFacts(
                as_of=TODAY, classification="non_bailable", triable_by_magistrate=True,
                first_evidence_date=date(2026, 1, 1), in_custody_whole_trial_period=True,
            ),
            BailRoute.REGULAR,
        )
        assert result["dates"][0]["date"] == "2026-03-02"
        assert any("s.480(6)" in item for item in result["cautions"])

    def test_anticipatory_exclusion(self):
        result = route(BailFacts(as_of=TODAY, involves_bns_65_or_70_2=True), BailRoute.ANTICIPATORY)
        assert result["status"] == RouteStatus.BARRED_ON_TEXT

    def test_anticipatory_does_not_fit_someone_in_custody(self):
        result = route(BailFacts(as_of=TODAY, in_custody=True), BailRoute.ANTICIPATORY)
        assert result["status"] == RouteStatus.NOT_APPLICABLE

    def test_anticipatory_unknowns_are_named(self):
        result = route(BailFacts(as_of=TODAY), BailRoute.ANTICIPATORY)
        assert result["status"] == RouteStatus.DISCRETIONARY
        assert len(result["missing"]) == 3


class TestAcrossRoutes:
    def test_a_pre_commencement_date_raises_the_savings_clause(self):
        result = assess_bail(BailFacts(as_of=TODAY, arrested_on=date(2024, 6, 1)))
        notice = result["pre_bnss_notice"]
        assert notice["sources"][0]["section"] == "BNSS s.531(2)(a)"

    def test_a_post_commencement_date_does_not(self):
        assert assess_bail(BailFacts(as_of=TODAY, arrested_on=date(2024, 7, 1)))["pre_bnss_notice"] is None

    def test_no_finding_predicts_an_outcome(self):
        cases = [
            BailFacts(as_of=TODAY, classification="bailable"),
            BailFacts(as_of=TODAY, classification="non_bailable", punishable_with_death_or_life=True),
            BailFacts(as_of=TODAY, gravity=OffenceGravity.OTHER, first_remand_on=date(2026, 1, 1), report_filed=False),
        ]
        banned = ("will be granted", "will get", "likely", "chance", "should succeed", "will succeed")
        for facts in cases:
            text = str(assess_bail(facts)).casefold()
            assert not any(word in text for word in banned)

    def test_every_route_carries_a_source_for_what_it_says(self):
        for item in assess_bail(BailFacts(as_of=TODAY))["routes"]:
            assert item["sources"], item["route"]
            assert all(source["excerpt"] for source in item["sources"])
