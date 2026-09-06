"""A checklist that defaults to "done" certifies an investigation nobody checked.

Every test here is a way this could quietly report compliance that was
never established.
"""

from __future__ import annotations

import pytest

from app.services.investigation_compliance import (
    ComplianceStatus,
    PoliceAction,
    compliance_checklist,
    outstanding,
    unrecorded,
)


def _keys(items) -> set[str]:
    return {item.key for item in items}


class TestNothingIsAssumedDone:
    def test_an_empty_status_leaves_every_item_unrecorded(self) -> None:
        items = compliance_checklist(PoliceAction.ARREST)

        assert items
        assert all(i.status is ComplianceStatus.NOT_RECORDED for i in items)

    def test_unrecorded_is_not_reported_as_outstanding(self) -> None:
        """"Nobody wrote it down" and "it was not done" call for different
        action: one is a record to complete, the other a breach to remedy.
        Collapsing them makes a complete investigation look unlawful and an
        unlawful one look merely untidy."""
        items = compliance_checklist(PoliceAction.ARREST)

        assert outstanding(items) == []
        assert len(unrecorded(items)) == len(items)

    def test_a_positively_failed_item_is_outstanding(self) -> None:
        items = compliance_checklist(
            PoliceAction.ARREST,
            status={"memorandum_of_arrest": ComplianceStatus.NOT_SATISFIED},
        )

        assert _keys(outstanding(items)) == {"memorandum_of_arrest"}
        assert "memorandum_of_arrest" not in _keys(unrecorded(items))

    def test_a_satisfied_item_is_neither(self) -> None:
        items = compliance_checklist(
            PoliceAction.ARREST,
            status={"medical_examination": ComplianceStatus.SATISFIED},
        )

        assert "medical_examination" not in _keys(outstanding(items))
        assert "medical_examination" not in _keys(unrecorded(items))


class TestConditionalRequirements:
    def test_the_woman_safeguard_appears_only_when_it_applies(self) -> None:
        without = compliance_checklist(PoliceAction.ARREST)
        with_woman = compliance_checklist(PoliceAction.ARREST, arrested_person_is_woman=True)

        assert "woman_not_touched_by_male_officer" not in _keys(without)
        assert "woman_not_touched_by_male_officer" in _keys(with_woman)

    def test_the_handcuff_check_appears_only_when_handcuffs_were_used(self) -> None:
        assert "handcuff_ground_within_s43_3" not in _keys(
            compliance_checklist(PoliceAction.ARREST)
        )
        assert "handcuff_ground_within_s43_3" in _keys(
            compliance_checklist(PoliceAction.ARREST, handcuffs_used=True)
        )

    def test_s36c_drops_out_when_the_memorandum_was_attested_by_family(self) -> None:
        """The section says so expressly. Listing it anyway would leave a
        permanent outstanding item on a lawful arrest, which is how a
        checklist trains its user to ignore it."""
        items = compliance_checklist(
            PoliceAction.ARREST, memorandum_attested_by_family=True
        )

        assert "right_to_have_someone_informed" not in _keys(items)

    def test_it_is_present_by_default(self) -> None:
        assert "right_to_have_someone_informed" in _keys(
            compliance_checklist(PoliceAction.ARREST)
        )


class TestTheArrestChecklistIsComplete:
    @pytest.mark.parametrize(
        "key",
        [
            "grounds_recorded_in_writing",   # s.35(1)(b)
            "memorandum_of_arrest",          # s.36(b)
            "grounds_communicated",          # s.47(1)
            "relative_or_friend_informed",   # s.48(1)
            "station_book_entry",            # s.48(3)
            "medical_examination",           # s.53
        ],
    )
    def test_each_core_safeguard_is_present(self, key: str) -> None:
        """These are the six that apply to every arrest.

        An omitted row reads as an inapplicable rule, so dropping one
        silently removes a safeguard rather than failing.
        """
        assert key in _keys(compliance_checklist(PoliceAction.ARREST))


class TestTheSearchChecklistIsComplete:
    @pytest.mark.parametrize(
        "key",
        [
            "grounds_in_case_diary",              # s.185(1)
            "independent_witnesses",              # s.103(4)
            "seizure_list",                       # s.103(5)
            "audio_video_recording",              # s.105
            "recording_forwarded_to_magistrate",  # s.105
        ],
    )
    def test_each_search_requirement_is_present(self, key: str) -> None:
        assert key in _keys(compliance_checklist(PoliceAction.SEARCH_AND_SEIZURE))

    def test_recording_and_forwarding_are_separate_obligations(self) -> None:
        """s.105 requires both. Making the recording and never sending it is
        a breach, and one combined row lets a half-done obligation be
        ticked."""
        items = compliance_checklist(PoliceAction.SEARCH_AND_SEIZURE)
        recording = {i.key for i in items if i.provision == "BNSS s.105"}

        assert recording == {"audio_video_recording", "recording_forwarded_to_magistrate"}


class TestEveryItemCitesItsProvision:
    @pytest.mark.parametrize("action", list(PoliceAction))
    def test_no_requirement_is_unattributed(self, action) -> None:
        """An uncheckable requirement asks to be believed."""
        for item in compliance_checklist(action, arrested_person_is_woman=True, handcuffs_used=True):
            assert item.provision.startswith("BNSS s."), item.key
            assert item.requirement.strip()
            assert item.consequence.strip()

    def test_a_conditional_item_says_why_it_applies(self, ) -> None:
        items = compliance_checklist(PoliceAction.ARREST, handcuffs_used=True)
        conditional = next(i for i in items if i.key == "handcuff_ground_within_s43_3")

        assert conditional.applies_because == "handcuffs were used"


class TestTheCaseDiary:
    @pytest.mark.parametrize(
        "key",
        [
            "day_by_day_entries",
            "time_information_reached",
            "times_investigation_opened_and_closed",
            "places_visited",
            "circumstances_ascertained",
            "section_180_statements_inserted",
            "volume_is_paginated",
        ],
    )
    def test_each_s192_requirement_is_present(self, key: str) -> None:
        assert key in _keys(compliance_checklist(PoliceAction.CASE_DIARY))

    def test_pagination_is_its_own_requirement(self) -> None:
        """s.192(3) is what makes a later insertion visible.

        A court may send for the diary under s.192(4). Folding pagination
        into "keep a diary" would let an unpaginated one be ticked as
        compliant, which defeats the only check the section provides.
        """
        item = next(
            i
            for i in compliance_checklist(PoliceAction.CASE_DIARY)
            if i.key == "volume_is_paginated"
        )

        assert item.provision == "BNSS s.192(3)"


class TestTheFinalReport:
    @pytest.mark.parametrize(
        ("key", "clause"),
        [
            ("names_of_parties", "(a)"),
            ("nature_of_information", "(b)"),
            ("persons_acquainted_with_circumstances", "(c)"),
            ("whether_an_offence_appears_committed", "(d)"),
            ("whether_accused_arrested", "(e)"),
            ("whether_released_on_bond", "(f)"),
            ("whether_forwarded_in_custody", "(g)"),
        ],
    )
    def test_every_unconditional_clause_is_present(self, key: str, clause: str) -> None:
        items = {i.key: i for i in compliance_checklist(PoliceAction.FINAL_REPORT)}

        assert key in items
        assert items[key].provision.endswith(clause)

    def test_the_medical_report_clause_is_conditional(self) -> None:
        """Clause (h) applies only to the listed sexual offences.

        Listing it on every report would leave a permanent outstanding item
        on an ordinary theft, which teaches the user to ignore the list.
        """
        assert "medical_examination_report_attached" not in _keys(
            compliance_checklist(PoliceAction.FINAL_REPORT)
        )
        assert "medical_examination_report_attached" in _keys(
            compliance_checklist(PoliceAction.FINAL_REPORT, is_listed_sexual_offence=True)
        )

    def test_the_electronic_custody_clause_is_conditional(self) -> None:
        """Clause (i) is new in the BNSS and has no CrPC ancestor.

        An unbroken custody sequence is what makes a device's contents
        provable; without it the evidence is open to challenge whatever it
        contains. It is the clause most easily missed, because nothing in
        the old form asked for it.
        """
        assert "electronic_device_custody_sequence" not in _keys(
            compliance_checklist(PoliceAction.FINAL_REPORT)
        )
        assert "electronic_device_custody_sequence" in _keys(
            compliance_checklist(PoliceAction.FINAL_REPORT, electronic_device_seized=True)
        )


class TestTheActionsDoNotLeakIntoEachOther:
    def test_an_arrest_flag_does_not_change_the_case_diary(self) -> None:
        plain = _keys(compliance_checklist(PoliceAction.CASE_DIARY))
        flagged = _keys(
            compliance_checklist(
                PoliceAction.CASE_DIARY,
                arrested_person_is_woman=True,
                handcuffs_used=True,
                electronic_device_seized=True,
            )
        )

        assert plain == flagged

    @pytest.mark.parametrize("action", list(PoliceAction))
    def test_every_action_produces_a_distinct_non_empty_list(self, action) -> None:
        assert compliance_checklist(action), f"{action} has no requirements"

    def test_no_requirement_key_appears_under_two_actions(self) -> None:
        """Keys are the storage identity. A key shared between two actions
        would let a confirmation recorded against one tick the other."""
        seen: dict[str, str] = {}
        for action in PoliceAction:
            for item in compliance_checklist(
                action,
                is_listed_sexual_offence=True,
                electronic_device_seized=True,
                arrested_person_is_woman=True,
                handcuffs_used=True,
            ):
                assert item.key not in seen, (
                    f"{item.key!r} appears under both {seen.get(item.key)} and {action}"
                )
                seen[item.key] = str(action)
