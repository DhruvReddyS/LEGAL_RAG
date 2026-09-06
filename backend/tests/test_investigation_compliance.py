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
