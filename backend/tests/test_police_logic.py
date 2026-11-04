"""The police tools' judgment calls, without a database.

Each test is a way these could report something the record does not support.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.enums import OffenceGravity
from app.services.investigation_compliance import PoliceAction, compliance_checklist
from app.services.investigation_timeline import Deadline, InvestigationFacts, investigation_deadlines
from app.services.police_case_file import render_case_file
from app.services.police_custody import (
    ChainState,
    CustodyHop,
    RemandPeriod,
    analyse_chain,
    diary_gaps,
    remand_summary,
)
from app.services.police_drafting import BANNER, DRAFT_TYPES, DraftContext, render_draft
from app.services.police_offences import OFFENCES, ElementState, OverallFinding, assess, overall_finding
from app.services.police_register import (
    RegisterState,
    classify,
    derived_completions,
    register_rows,
    search_record_deadline,
    sort_rows,
    summarise,
)
from app.services.police_search_check import CheckVerdict, SearchRecord, evaluate_search, overall

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 6, 15, 12, tzinfo=IST)


def _deadline(due: datetime | None, **extra) -> Deadline:
    return Deadline(
        key=extra.pop("key", "k"),
        obligation="Do it.",
        provision="BNSS s.58",
        due_at=due,
        consequence="c",
        computed_from="f",
        undetermined_because="" if due else "a date is missing",
        **extra,
    )


class TestTheFourWordsMeanDifferentThings:
    def test_an_expired_limit_with_no_record_is_overdue_not_breached(self) -> None:
        """It may have been done without being written down. Calling that a breach
        convicts an officer of a missing entry."""
        state, reason, _ = classify(_deadline(NOW - timedelta(days=1)), None, NOW)

        assert state is RegisterState.OVERDUE
        assert "no completion" in reason

    def test_a_late_completion_is_a_breach(self) -> None:
        state, _, _ = classify(_deadline(NOW - timedelta(days=2)), NOW - timedelta(days=1), NOW)

        assert state is RegisterState.BREACHED

    def test_a_timely_completion_is_met_even_after_the_limit_passes(self) -> None:
        state, _, _ = classify(_deadline(NOW - timedelta(days=1)), NOW - timedelta(days=2), NOW)

        assert state is RegisterState.MET

    def test_an_uncomputable_limit_is_unknown_never_due_or_overdue(self) -> None:
        state, reason, imminent = classify(_deadline(None), None, NOW)

        assert state is RegisterState.UNKNOWN
        assert "Cannot be determined" in reason
        assert imminent is False

    def test_a_completion_cannot_rescue_an_uncomputable_limit(self) -> None:
        state, _, _ = classify(_deadline(None), NOW, NOW)

        assert state is RegisterState.UNKNOWN

    def test_production_after_the_earliest_expiry_cannot_be_called_a_breach(self) -> None:
        """s.58 excludes the journey, which nobody recorded. An hour after the computed
        moment may be well inside the true limit."""
        state, reason, _ = classify(
            _deadline(NOW - timedelta(hours=2), is_earliest_possible=True), NOW - timedelta(hours=1), NOW
        )

        assert state is RegisterState.UNKNOWN
        assert "Journey" in reason

    @pytest.mark.parametrize(("hours", "imminent"), [(47, True), (49, False)])
    def test_imminent_is_a_flag_on_due(self, hours: int, imminent: bool) -> None:
        state, _, flagged = classify(_deadline(NOW + timedelta(hours=hours)), None, NOW)

        assert state is RegisterState.DUE
        assert flagged is imminent


class TestCompletionsTheDatesAlreadyEstablish:
    def test_a_first_remand_establishes_production_but_nothing_else(self) -> None:
        derived = derived_completions(InvestigationFacts(first_remand_at=NOW))

        assert derived == {"production_before_magistrate": NOW}

    def test_a_forwarded_report_answers_the_investigation_limits(self) -> None:
        derived = derived_completions(InvestigationFacts(police_report_forwarded_at=NOW))

        assert set(derived) == {"default_bail_entitlement", "investigation_completion"}

    def test_accused_produced_is_not_read_as_first_production(self) -> None:
        """That field is s.230's production, after the report."""
        assert derived_completions(InvestigationFacts(accused_produced_at=NOW)) == {}

    def test_what_the_officer_stated_beats_what_the_dates_imply(self) -> None:
        later = NOW + timedelta(hours=1)
        row = register_rows(
            case_id="c", case_title="t",
            deadlines=[_deadline(NOW + timedelta(days=1), key="production_before_magistrate")],
            completions={"production_before_magistrate": (later, "note")},
            derived={"production_before_magistrate": NOW},
            now=NOW,
        )[0]

        assert row.completed_at == later
        assert row.completion_is_derived is False


def _rows(*deadlines: Deadline, completions=None):
    return register_rows(
        case_id="c", case_title="t", deadlines=list(deadlines),
        completions=completions or {}, derived={}, now=NOW,
    )


class TestRegisterOrderAndCounts:
    def test_overdue_and_imminent_come_before_everything_else(self) -> None:
        rows = _rows(
            _deadline(NOW + timedelta(days=30), key="later"),
            _deadline(None, key="unknown"),
            _deadline(NOW - timedelta(days=1), key="overdue"),
            _deadline(NOW + timedelta(hours=5), key="imminent"),
        )

        assert [r.key for r in sort_rows(rows)][:2] == ["overdue", "imminent"]

    def test_a_magistrates_duty_sinks_and_is_not_counted_as_the_officers(self) -> None:
        rows = _rows(
            _deadline(NOW - timedelta(days=1), key="magistrate", actor="magistrate"),
            _deadline(NOW + timedelta(days=30), key="mine"),
        )

        assert sort_rows(rows)[0].key == "mine"
        counts = summarise(rows)
        assert counts["overdue"] == 0
        assert counts["not_officer_duty"] == 1

    def test_unknown_is_counted_as_unknown(self) -> None:
        counts = summarise(_rows(_deadline(None)))

        assert counts["unknown"] == 1
        assert counts["met"] == 0 and counts["breached"] == 0


class TestSearchRecordDeadline:
    def test_forty_eight_hours_from_the_grounds(self) -> None:
        deadline = search_record_deadline("id", "the shed", NOW)

        assert deadline.due_at == NOW + timedelta(hours=48)
        assert deadline.provision == "BNSS s.185(5)"
        assert "shed" not in deadline.obligation, "a supervisor reads this field"

    def test_without_the_grounds_time_it_is_undetermined(self) -> None:
        assert search_record_deadline("id", "x", None).due_at is None


def _verdicts(record: SearchRecord) -> dict[str, CheckVerdict]:
    return {c.key: c.verdict for c in evaluate_search(record, NOW)}


class TestSearchCheck:
    def test_nothing_recorded_finds_nothing_either_way(self) -> None:
        checks = evaluate_search(SearchRecord(basis="section_185"), NOW)

        assert {c.verdict for c in checks} == {CheckVerdict.CANNOT_BE_DETERMINED}
        assert overall(checks)["finding"] == "incomplete_record"

    def test_one_witness_is_a_failure_of_s103_4(self) -> None:
        assert _verdicts(SearchRecord(witness_count=1))["two_or_more_witnesses"] is CheckVerdict.NOT_MET
        assert _verdicts(SearchRecord(witness_count=2))["two_or_more_witnesses"] is CheckVerdict.MET

    def test_zero_witnesses_is_not_the_same_as_not_recorded(self) -> None:
        assert _verdicts(SearchRecord(witness_count=0))["two_or_more_witnesses"] is CheckVerdict.NOT_MET
        assert _verdicts(SearchRecord())["two_or_more_witnesses"] is CheckVerdict.CANNOT_BE_DETERMINED

    def test_grounds_recorded_after_the_search_fail_on_the_recorded_times(self) -> None:
        record = SearchRecord(
            basis="section_185", searched_at=NOW, grounds_recorded_at=NOW + timedelta(hours=1)
        )

        assert _verdicts(record)["grounds_recorded_before_search"] is CheckVerdict.NOT_MET

    def test_the_48_hours_are_computed(self) -> None:
        grounds = NOW - timedelta(days=5)
        on_time = SearchRecord(
            basis="section_185", grounds_recorded_at=grounds,
            record_sent_to_magistrate_at=grounds + timedelta(hours=47),
        )
        late = SearchRecord(
            basis="section_185", grounds_recorded_at=grounds,
            record_sent_to_magistrate_at=grounds + timedelta(hours=49),
        )
        unsent = SearchRecord(basis="section_185", grounds_recorded_at=grounds)

        assert _verdicts(on_time)["record_copies_within_48_hours"] is CheckVerdict.MET
        assert _verdicts(late)["record_copies_within_48_hours"] is CheckVerdict.NOT_MET
        # Not sending and not recording that it was sent are different things.
        assert _verdicts(unsent)["record_copies_within_48_hours"] is CheckVerdict.CANNOT_BE_DETERMINED

    def test_a_warrant_search_is_not_held_to_section_185(self) -> None:
        verdicts = _verdicts(SearchRecord(basis="warrant"))

        assert "grounds_recorded_before_search" not in verdicts
        assert "record_copies_within_48_hours" not in verdicts
        assert "within_station_limits" not in verdicts

    def test_an_unknown_basis_cannot_exclude_section_185(self) -> None:
        verdicts = _verdicts(SearchRecord(basis="unknown"))

        assert verdicts["basis_recorded"] is CheckVerdict.CANNOT_BE_DETERMINED
        assert verdicts["within_station_limits"] is CheckVerdict.CANNOT_BE_DETERMINED

    def test_an_unknown_basis_stays_unknown_even_with_a_yes(self) -> None:
        verdicts = _verdicts(SearchRecord(basis="unknown", answers={"within_station_limits": "yes"}))

        assert verdicts["within_station_limits"] is CheckVerdict.CANNOT_BE_DETERMINED

    def test_a_conditional_row_needs_its_condition(self) -> None:
        unknown = _verdicts(SearchRecord())
        applies = _verdicts(SearchRecord(answers={"woman_searched": "yes", "woman_searched_by_woman": "no"}))
        excluded = _verdicts(SearchRecord(answers={"woman_searched": "no"}))

        assert unknown["woman_searched_by_woman"] is CheckVerdict.CANNOT_BE_DETERMINED
        assert applies["woman_searched_by_woman"] is CheckVerdict.NOT_MET
        assert "woman_searched_by_woman" not in excluded

    def test_no_finding_is_a_ruling_on_legality(self) -> None:
        answers = {key: "yes" for key in (
            "witnesses_independent", "search_in_witnesses_presence", "seizure_list_prepared",
            "seizure_list_signed", "occupant_allowed_to_attend", "list_copy_to_occupant",
            "audio_video_recorded",
        )}
        answers.update({"place_was_closed": "no", "person_searched": "no", "woman_searched": "no", "seized_under_s106": "no"})
        checks = evaluate_search(
            SearchRecord(basis="warrant", witness_count=2, answers=answers, recording_forwarded_at=NOW), NOW
        )

        assert overall(checks)["finding"] == "no_defect_on_record"
        assert all("legal" not in str(overall(checks)["finding"]) for _ in checks)

    def test_a_single_failure_outranks_any_number_of_unknowns(self) -> None:
        checks = evaluate_search(SearchRecord(witness_count=1), NOW)

        assert overall(checks)["finding"] == "defect_on_record"

    def test_every_check_names_a_sub_section(self) -> None:
        for check in evaluate_search(SearchRecord(basis="unknown"), NOW):
            assert check.provision.startswith("BNSS s."), check.key


T = NOW - timedelta(days=10)


def _hop(n: int, source: str, target: str, **extra) -> CustodyHop:
    return CustodyHop(id=str(n), occurred_at=T + timedelta(hours=n), from_person=source, to_person=target, **extra)


class TestChainOfCustody:
    def test_each_hand_over_from_the_last_holder_is_continuous(self) -> None:
        finding = analyse_chain(seized_by="SI Rao", seized_at=T, hops=[_hop(1, "SI Rao", "HC Das"), _hop(2, "HC Das", "FSL")])

        assert finding.state is ChainState.CONTINUOUS
        assert finding.current_holder == "FSL"

    def test_a_hand_over_from_someone_else_is_a_break(self) -> None:
        finding = analyse_chain(seized_by="SI Rao", seized_at=T, hops=[_hop(1, "HC Das", "FSL")])

        assert finding.state is ChainState.BROKEN
        assert "HC Das" in finding.issues[0] and "SI Rao" in finding.issues[0]

    def test_case_and_spacing_do_not_break_a_chain(self) -> None:
        finding = analyse_chain(seized_by="SI  Rao", seized_at=T, hops=[_hop(1, "si rao", "FSL")])

        assert finding.state is ChainState.CONTINUOUS

    def test_a_different_name_for_maybe_the_same_person_is_a_break(self) -> None:
        """The two entries do not say the same person held it."""
        finding = analyse_chain(seized_by="SI Rao", seized_at=T, hops=[_hop(1, "Rao", "FSL")])

        assert finding.state is ChainState.BROKEN

    def test_no_seizing_officer_is_undetermined_not_continuous(self) -> None:
        finding = analyse_chain(seized_by=None, seized_at=T, hops=[_hop(1, "A", "B")])

        assert finding.state is ChainState.CANNOT_BE_DETERMINED

    def test_a_hand_over_dated_before_the_seizure_is_a_break(self) -> None:
        early = CustodyHop(id="1", occurred_at=T - timedelta(days=1), from_person="SI Rao", to_person="FSL")

        assert analyse_chain(seized_by="SI Rao", seized_at=T, hops=[early]).state is ChainState.BROKEN

    def test_a_correction_replaces_the_entry_it_names(self) -> None:
        wrong = _hop(1, "HC Das", "FSL")
        fixed = _hop(2, "SI Rao", "FSL", corrects_event_id="1")

        assert analyse_chain(seized_by="SI Rao", seized_at=T, hops=[wrong, fixed]).state is ChainState.CONTINUOUS

    def test_no_hand_over_leaves_it_with_the_seizing_officer(self) -> None:
        finding = analyse_chain(seized_by="SI Rao", seized_at=T, hops=[])

        assert finding.state is ChainState.CONTINUOUS
        assert finding.current_holder == "SI Rao"


class TestRemand:
    def _summary(self, *periods: RemandPeriod, gravity=OffenceGravity.OTHER, today=date(2026, 1, 20)):
        return remand_summary(
            list(periods), first_remand_at=datetime(2026, 1, 1, 10, tzinfo=IST), gravity=gravity, today=today
        )

    def test_both_ends_count_as_whole_days(self) -> None:
        summary = self._summary(RemandPeriod("police", date(2026, 1, 1), date(2026, 1, 5)))

        assert summary.police_days_used == 5
        assert summary.police_days_left == 10

    def test_more_than_fifteen_police_days_is_a_finding(self) -> None:
        summary = self._summary(RemandPeriod("police", date(2026, 1, 1), date(2026, 1, 16)))

        assert summary.police_days_left == 0
        assert any("fifteen" in finding for finding in summary.findings)

    def test_judicial_custody_does_not_use_the_fifteen(self) -> None:
        summary = self._summary(RemandPeriod("judicial", date(2026, 1, 1), date(2026, 1, 30)))

        assert summary.police_days_used == 0
        assert summary.judicial_days == 30

    def test_the_window_follows_the_gravity(self) -> None:
        assert self._summary().window_days == 40
        grave = self._summary(gravity=OffenceGravity.DEATH_LIFE_OR_TEN_YEARS_OR_MORE)
        assert grave.window_days == 60
        assert grave.police_custody_window_ends == date(2026, 3, 1)

    def test_unknown_gravity_gives_no_window(self) -> None:
        summary = self._summary(gravity=OffenceGravity.UNKNOWN)

        assert summary.police_custody_window_ends is None
        assert "gravity" in summary.undetermined_because

    def test_police_custody_past_the_window_is_a_finding(self) -> None:
        summary = self._summary(RemandPeriod("police", date(2026, 2, 8), date(2026, 2, 12)), today=date(2026, 2, 13))

        assert any("runs past" in finding for finding in summary.findings)


class TestDiaryGaps:
    def test_days_without_an_entry_are_listed(self) -> None:
        assert diary_gaps([date(2026, 1, 1), date(2026, 1, 3)], until=date(2026, 1, 4)) == [
            date(2026, 1, 2), date(2026, 1, 4),
        ]

    def test_an_empty_diary_has_no_gaps_to_compute(self) -> None:
        assert diary_gaps([], until=date(2026, 1, 4)) == []


class TestOffenceAssessment:
    def test_nothing_recorded_is_undetermined(self) -> None:
        elements = assess(OFFENCES["theft"], None)

        assert {e["state"] for e in elements} == {ElementState.CANNOT_BE_DETERMINED.value}
        assert overall_finding(elements) is OverallFinding.CANNOT_BE_DETERMINED

    def test_established_with_nothing_behind_it_falls_back(self) -> None:
        elements = assess(OFFENCES["theft"], {"moved": {"state": "established"}})

        assert next(e for e in elements if e["key"] == "moved")["state"] == "cannot_be_determined"

    def test_one_failed_element_outranks_the_rest(self) -> None:
        offence = OFFENCES["cheating"]
        stored = {e.key: {"state": "established", "witness_ids": ["w"]} for e in offence.elements}
        stored["deception"] = {"state": "not_established"}

        assert overall_finding(assess(offence, stored)) is OverallFinding.ELEMENT_NOT_ESTABLISHED

    def test_all_supported_needs_every_element(self) -> None:
        offence = OFFENCES["cheating"]
        stored = {e.key: {"state": "established", "witness_ids": ["w"]} for e in offence.elements}

        assert overall_finding(assess(offence, stored)) is OverallFinding.ALL_ELEMENTS_SUPPORTED
        stored.pop("deception")
        assert overall_finding(assess(offence, stored)) is OverallFinding.CANNOT_BE_DETERMINED

    def test_a_tampered_state_is_not_trusted(self) -> None:
        elements = assess(OFFENCES["theft"], {"moved": {"state": "proven beyond doubt", "witness_ids": ["w"]}})

        assert next(e for e in elements if e["key"] == "moved")["state"] == "cannot_be_determined"

    def test_no_finding_says_the_offence_is_made_out(self) -> None:
        for finding in OverallFinding:
            assert "made_out" not in finding.value and "guilty" not in finding.value

    def test_common_offences_are_covered(self) -> None:
        assert {"murder", "theft", "rape", "cheating", "robbery", "criminal_breach_of_trust"} <= set(OFFENCES)

    def test_element_keys_are_unique_within_an_offence(self) -> None:
        for offence in OFFENCES.values():
            keys = [e.key for e in offence.elements]
            assert len(keys) == len(set(keys)), offence.key


def _context(**extra) -> DraftContext:
    return DraftContext(case_title="FIR 12 of 2026", officer_name="SI Rao", **extra)


class TestDrafts:
    @pytest.mark.parametrize("draft_type", sorted(DRAFT_TYPES))
    def test_every_draft_says_it_is_a_draft_at_both_ends(self, draft_type: str) -> None:
        draft = render_draft(draft_type, _context())

        assert draft.rendered_text.startswith(BANNER)
        assert draft.rendered_text.rstrip().endswith(BANNER)
        assert "not been signed, issued or filed" in draft.disclaimer
        assert draft.disclaimer in draft.rendered_text

    @pytest.mark.parametrize("draft_type", sorted(DRAFT_TYPES))
    def test_every_draft_names_its_provisions(self, draft_type: str) -> None:
        draft = render_draft(draft_type, _context())

        assert draft.provisions
        assert all(p.startswith("BNSS s.") for p in draft.provisions)

    @pytest.mark.parametrize("draft_type", sorted(DRAFT_TYPES))
    def test_a_missing_fact_is_marked_and_listed_not_left_blank(self, draft_type: str) -> None:
        draft = render_draft(draft_type, _context())

        assert draft.missing_fields
        assert "[NOT RECORDED:" in draft.rendered_text

    def test_an_input_fills_the_field_and_clears_it_from_missing(self) -> None:
        empty = render_draft("s35_3_notice", _context())
        filled = render_draft("s35_3_notice", _context(), {"person_name": "A. Kumar"})

        assert "name of the person noticed" in empty.missing_fields
        assert "name of the person noticed" not in filled.missing_fields
        assert "A. Kumar" in filled.rendered_text

    def test_the_notice_carries_s35_consequences(self) -> None:
        text = render_draft("s35_3_notice", _context()).rendered_text

        assert "section 35(5)" in text.lower() and "section 35(6)" in text.lower()

    def test_the_production_order_says_who_may_issue_it(self) -> None:
        assert "officer in charge" in render_draft("s94_production_order", _context()).rendered_text.lower()

    def test_the_seizure_memo_lists_the_inventory_with_places(self) -> None:
        text = render_draft(
            "seizure_memo",
            _context(
                evidence=[{"exhibit_label": "M-1", "description": "Knife", "seized_from": "kitchen", "search_id": None}],
                witnesses=[{"name": "Lata", "category": "search_witness"}],
            ),
        ).rendered_text

        assert "M-1: Knife" in text and "kitchen" in text and "Lata" in text

    def test_the_remand_application_reports_custody_used(self) -> None:
        text = render_draft(
            "remand_application", _context(remand={"police_days_used": 4, "police_days_left": 11})
        ).rendered_text

        assert "4 day(s)" in text and "Remaining: 11" in text

    def test_the_chargesheet_clauses_h_and_i_appear_only_when_they_apply(self) -> None:
        plain = render_draft("chargesheet_skeleton", _context()).rendered_text
        flagged = render_draft(
            "chargesheet_skeleton",
            _context(
                facts={"clause_h_applies": True},
                evidence=[{"exhibit_label": "E-1", "description": "Phone", "category": "electronic", "seized_by": "SI Rao"}],
            ),
        ).rendered_text

        assert "(h) Whether" not in plain and "(i) Sequence" not in plain
        assert "(h) Whether" in flagged and "(i) Sequence" in flagged

    def test_the_chargesheet_does_not_hide_that_the_state_form_governs(self) -> None:
        assert "form governs" in render_draft("chargesheet_skeleton", _context()).rendered_text

    def test_a_pocso_only_case_does_not_ask_for_the_woman_medical_report(self) -> None:
        text = render_draft(
            "chargesheet_skeleton", _context(facts={"is_listed_sexual_offence": True})
        ).rendered_text

        assert "(h) Whether" not in text


class TestCaseFile:
    def _data(self, **extra) -> dict:
        return {
            "case": {"title": "FIR 12", "status": "open", "created_at": NOW},
            "generated_at": NOW,
            "officer_name": "SI Rao",
            **extra,
        }

    def test_free_text_cannot_become_markup(self) -> None:
        hostile = "<script>alert(1)</script>"
        html = render_case_file(
            self._data(
                case={"title": hostile, "status": "open", "created_at": NOW},
                evidence=[{
                    "exhibit_label": hostile, "description": hostile, "category": "electronic",
                    "seized_by": hostile, "custody_events": [{
                        "occurred_at": NOW, "from_person": hostile, "to_person": hostile,
                    }],
                    "chain": {"state": "broken", "issues": [hostile], "current_holder": hostile},
                }],
                witnesses=[{"name": hostile, "category": "other", "status": "examined", "contact": hostile}],
                drafts=[{"title": hostile, "version": 1, "rendered_text": hostile}],
            )
        )

        assert "<script" not in html
        assert "&lt;script&gt;" in html

    def test_it_says_what_it_is_and_what_it_is_not(self) -> None:
        html = render_case_file(self._data())

        assert html.count("not a filed document") == 2

    def test_a_draft_cannot_be_mistaken_for_the_real_thing(self) -> None:
        html = render_case_file(self._data(drafts=[{"title": "Remand", "version": 2, "rendered_text": "x"}]))

        assert "DRAFT: Remand" in html
        assert "not signed, not issued, not filed" in html

    def test_an_empty_record_says_so_rather_than_printing_nothing(self) -> None:
        html = render_case_file(self._data())

        assert "Nothing is on the inventory" in html
        assert "That is not a finding that none applies" in html

    def test_contact_details_stay_out_unless_asked_for(self) -> None:
        witness = {"name": "Lata", "category": "other", "status": "examined", "contact": "98765"}

        assert "98765" not in render_case_file(self._data(witnesses=[witness]))
        assert "98765" in render_case_file(self._data(witnesses=[witness], include_witness_contact=True))


class TestComplianceAdditions:
    def _keys(self, action=PoliceAction.ARREST, **flags) -> dict:
        return {item.key: item for item in compliance_checklist(action, **flags)}

    def test_the_sunset_row_appears_for_a_woman(self) -> None:
        """POL-6. A woman arrested at night used to get no row about it."""
        assert "woman_not_arrested_after_sunset" not in self._keys()
        assert self._keys(arrested_person_is_woman=True)["woman_not_arrested_after_sunset"].provision == "BNSS s.43(5)"

    def test_the_bail_right_row_is_conditional(self) -> None:
        assert "bail_right_informed" not in self._keys()
        assert self._keys(bailable_arrest_without_warrant=True)["bail_right_informed"].provision == "BNSS s.47(2)"

    def test_s48_2_is_on_every_arrest(self) -> None:
        assert self._keys()["rights_told_at_the_station"].provision == "BNSS s.48(2)"

    def test_s185_5_is_on_the_search_list(self) -> None:
        assert self._keys(PoliceAction.SEARCH_AND_SEIZURE)["record_copies_to_magistrate"].provision == "BNSS s.185(5)"

    def test_every_timeline_row_still_cites_a_section(self) -> None:
        facts = InvestigationFacts(
            information_recorded_at=NOW, arrested_at=NOW, is_rape_or_attempt=True, is_listed_sexual_offence=True,
        )
        for deadline in investigation_deadlines(facts):
            assert deadline.provision.startswith("BNSS s."), deadline.key
