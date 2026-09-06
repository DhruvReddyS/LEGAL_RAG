"""What the BNSS requires to be recorded, for the action actually taken.

The companion to investigation_timeline: that answers "by when", this
answers "what must exist". Both are read out of the Sanhita and neither
consults a model, for the same reason -- a fluent list of safeguards that
omits the memorandum of arrest is worse than no list, because the officer
stops looking.

The one rule that shapes everything here: an item nobody has confirmed is
NOT_RECORDED, never SATISFIED. A checklist whose default is "done" is a
checklist that certifies an investigation nobody checked, and the gap
between "we did this" and "nobody said" is the entire value of the
instrument.

Requirements that do not apply on these facts are omitted. Requirements
that apply are always listed, satisfied or not, because an omitted row and
an inapplicable rule look identical to whoever reads the output.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "ComplianceItem",
    "ComplianceStatus",
    "PoliceAction",
    "compliance_checklist",
    "outstanding",
    "unrecorded",
]


class PoliceAction(StrEnum):
    ARREST = "arrest"
    SEARCH_AND_SEIZURE = "search_and_seizure"
    CASE_DIARY = "case_diary"
    FINAL_REPORT = "final_report"


class ComplianceStatus(StrEnum):
    SATISFIED = "satisfied"
    NOT_SATISFIED = "not_satisfied"
    # The default. Distinct from NOT_SATISFIED because "we did not do this"
    # and "nobody recorded whether we did" call for different action: the
    # first is a breach to remedy, the second is a record to complete.
    NOT_RECORDED = "not_recorded"


@dataclass(frozen=True)
class ComplianceItem:
    key: str
    requirement: str
    provision: str
    consequence: str
    status: ComplianceStatus = ComplianceStatus.NOT_RECORDED
    # Why this row is on the list at all, for the conditional ones.
    applies_because: str = ""

    @property
    def is_outstanding(self) -> bool:
        """Positively not done. An unrecorded item is not outstanding."""
        return self.status is ComplianceStatus.NOT_SATISFIED


# Every requirement below was read out of the BNSS text in this corpus.
_ARREST: tuple[tuple[str, str, str, str], ...] = (
    (
        "grounds_recorded_in_writing",
        "Record in writing the reasons for making the arrest.",
        "BNSS s.35(1)(b)",
        "The Sanhita requires the reasons to be recorded while making the arrest. "
        "It equally requires reasons in writing where an arrest is not made.",
    ),
    (
        "memorandum_of_arrest",
        "Prepare a memorandum of arrest, attested by a family member of the "
        "arrested person or a respectable member of the locality, and "
        "countersigned by the arrested person.",
        "BNSS s.36(b)",
        "Both the attestation and the countersignature are required; a memorandum "
        "carrying neither is not the document the section describes.",
    ),
    (
        "right_to_have_someone_informed",
        "Tell the arrested person of the right to have a relative, friend or "
        "nominated person informed of the arrest.",
        "BNSS s.36(c)",
        "Required unless the memorandum was attested by a member of the family.",
    ),
    (
        "grounds_communicated",
        "Communicate full particulars of the offence, or the other grounds for "
        "the arrest, forthwith.",
        "BNSS s.47(1)",
        "Forthwith, not at first production. A delayed communication is a breach "
        "even if the particulars are eventually given.",
    ),
    (
        "relative_or_friend_informed",
        "Inform a relative, friend or nominated person of the arrest and of where "
        "the arrested person is held, and inform the designated police officer "
        "for the district.",
        "BNSS s.48(1)",
        "Both notifications are required, not either.",
    ),
    (
        "station_book_entry",
        "Enter in the police station book who was informed of the arrest.",
        "BNSS s.48(3)",
        "The entry is the proof that s.48(1) was complied with.",
    ),
    (
        "medical_examination",
        "Have the arrested person examined by a medical officer in government "
        "service, or a registered medical practitioner if none is available.",
        "BNSS s.53",
        "Soon after the arrest. It protects the arrested person and the officer "
        "alike, and its absence is the gap every custodial-injury allegation "
        "occupies.",
    ),
)

_SEARCH: tuple[tuple[str, str, str, str], ...] = (
    (
        "grounds_in_case_diary",
        "Record in the case diary the grounds of belief for the search, "
        "specifying so far as possible the thing to be searched for.",
        "BNSS s.185(1)",
        "Recorded before the search, not reconstructed after it.",
    ),
    (
        "independent_witnesses",
        "Call two or more independent and respectable inhabitants of the locality "
        "to attend and witness the search.",
        "BNSS s.103(4)",
        "Two or more, independent, and of the locality where practicable.",
    ),
    (
        "seizure_list",
        "Prepare a list of everything seized and of the place in which each thing "
        "was found, signed by the witnesses.",
        "BNSS s.103(5)",
        "The list records where each item was found, not merely what was taken.",
    ),
    (
        "audio_video_recording",
        "Record the search and seizure, including the preparation and signing of "
        "the seizure list, through audio-video electronic means.",
        "BNSS s.105",
        "Mandatory under the BNSS, and the recording must be forwarded to the "
        "Magistrate without delay. This is new: the CrPC had no equivalent.",
    ),
    (
        "recording_forwarded_to_magistrate",
        "Forward the audio-video recording to the District Magistrate, "
        "Sub-divisional Magistrate or Judicial Magistrate of the first class.",
        "BNSS s.105",
        "Making the recording is not the whole obligation; forwarding it is part "
        "of the same section.",
    ),
)


_CASE_DIARY: tuple[tuple[str, str, str, str], ...] = (
    (
        "day_by_day_entries",
        "Enter the proceedings in the investigation day by day.",
        "BNSS s.192(1)",
        "Day by day, not reconstructed at the end. A diary written afterwards "
        "is not the record the section describes.",
    ),
    (
        "time_information_reached",
        "Record the time at which the information reached the officer.",
        "BNSS s.192(1)",
        "One of four times the sub-section names explicitly.",
    ),
    (
        "times_investigation_opened_and_closed",
        "Record the time the investigation began and the time it closed, each day.",
        "BNSS s.192(1)",
        "Both times, for each day's proceedings.",
    ),
    (
        "places_visited",
        "Record the place or places visited.",
        "BNSS s.192(1)",
        "The diary is the only contemporaneous record of where the "
        "investigation went.",
    ),
    (
        "circumstances_ascertained",
        "Record a statement of the circumstances ascertained through the "
        "investigation.",
        "BNSS s.192(1)",
        "The substance, not merely the movements.",
    ),
    (
        "section_180_statements_inserted",
        "Insert the witness statements recorded under s.180 into the case diary.",
        "BNSS s.192(2)",
        "Inserted into the diary itself, not merely filed alongside it.",
    ),
    (
        "volume_is_paginated",
        "Keep the diary as a volume, duly paginated.",
        "BNSS s.192(3)",
        "Pagination is what makes a later insertion visible. A court may send "
        "for the diary under s.192(4).",
    ),
)

# s.193(3)(i)(a)-(i). Clauses (h) and (i) are new in the BNSS and are the two
# most often missed, because nothing in the old CrPC form asked for them.
_FINAL_REPORT: tuple[tuple[str, str, str, str], ...] = (
    ("names_of_parties", "State the names of the parties.", "BNSS s.193(3)(i)(a)", "Clause (a)."),
    ("nature_of_information", "State the nature of the information.", "BNSS s.193(3)(i)(b)", "Clause (b)."),
    (
        "persons_acquainted_with_circumstances",
        "Name the persons who appear to be acquainted with the circumstances of the case.",
        "BNSS s.193(3)(i)(c)",
        "Clause (c). These are the prosecution's potential witnesses.",
    ),
    (
        "whether_an_offence_appears_committed",
        "State whether any offence appears to have been committed and, if so, by whom.",
        "BNSS s.193(3)(i)(d)",
        "Clause (d). The report must reach a conclusion, not merely narrate.",
    ),
    ("whether_accused_arrested", "State whether the accused has been arrested.", "BNSS s.193(3)(i)(e)", "Clause (e)."),
    (
        "whether_released_on_bond",
        "State whether the accused has been released on bond or bail bond.",
        "BNSS s.193(3)(i)(f)",
        "Clause (f).",
    ),
    (
        "whether_forwarded_in_custody",
        "State whether the accused has been forwarded in custody under s.190.",
        "BNSS s.193(3)(i)(g)",
        "Clause (g).",
    ),
)


def compliance_checklist(
    action: PoliceAction,
    *,
    status: dict[str, ComplianceStatus] | None = None,
    arrested_person_is_woman: bool = False,
    handcuffs_used: bool = False,
    memorandum_attested_by_family: bool = False,
    is_listed_sexual_offence: bool = False,
    electronic_device_seized: bool = False,
) -> list[ComplianceItem]:
    """The requirements that apply to this action, with what is known of each.

    ``status`` carries only what has been positively established. Anything
    absent stays NOT_RECORDED: the checklist never assumes an obligation was
    met because nobody said otherwise.
    """
    known = status or {}
    rows: list[tuple[str, str, str, str, str]] = []

    if action is PoliceAction.ARREST:
        for key, requirement, provision, consequence in _ARREST:
            if key == "right_to_have_someone_informed" and memorandum_attested_by_family:
                # s.36(c) is expressly conditional. Listing it anyway would
                # generate a permanent outstanding item on a lawful arrest.
                continue
            rows.append((key, requirement, provision, consequence, ""))

        if arrested_person_is_woman:
            rows.append((
                "woman_not_touched_by_male_officer",
                "Presume submission to custody on oral intimation, and do not "
                "touch the woman to effect the arrest unless the officer is female.",
                "BNSS s.43(1) proviso",
                "The proviso is unconditional unless the circumstances indicate "
                "otherwise or the officer is female.",
                "the arrested person is a woman",
            ))
        if handcuffs_used:
            rows.append((
                "handcuff_ground_within_s43_3",
                "Confirm the ground for handcuffing falls within s.43(3): a "
                "habitual or repeat offender, escape from custody, or one of the "
                "offences the sub-section lists.",
                "BNSS s.43(3)",
                "The power is confined to the listed cases; the nature and gravity "
                "of the offence must also have been considered.",
                "handcuffs were used",
            ))
    elif action is PoliceAction.SEARCH_AND_SEIZURE:
        for key, requirement, provision, consequence in _SEARCH:
            rows.append((key, requirement, provision, consequence, ""))
    elif action is PoliceAction.CASE_DIARY:
        for key, requirement, provision, consequence in _CASE_DIARY:
            rows.append((key, requirement, provision, consequence, ""))
    else:
        for key, requirement, provision, consequence in _FINAL_REPORT:
            rows.append((key, requirement, provision, consequence, ""))

        if is_listed_sexual_offence:
            rows.append((
                "medical_examination_report_attached",
                "Attach the report of the medical examination of the woman.",
                "BNSS s.193(3)(i)(h)",
                "Required where the investigation relates to BNS ss.64-68, 70 or "
                "71. New in the BNSS; the old CrPC form did not ask for it.",
                "the offence is one of those listed in clause (h)",
            ))
        if electronic_device_seized:
            rows.append((
                "electronic_device_custody_sequence",
                "State the sequence of custody for the electronic device.",
                "BNSS s.193(3)(i)(i)",
                "New in the BNSS. An unbroken custody sequence is what makes the "
                "device's contents provable; without it the evidence is open to "
                "challenge whatever it contains.",
                "an electronic device was seized",
            ))

    return [
        ComplianceItem(
            key=key,
            requirement=requirement,
            provision=provision,
            consequence=consequence,
            status=known.get(key, ComplianceStatus.NOT_RECORDED),
            applies_because=because,
        )
        for key, requirement, provision, consequence, because in rows
    ]


def outstanding(items: list[ComplianceItem]) -> list[ComplianceItem]:
    """Only those positively not done."""
    return [item for item in items if item.is_outstanding]


def unrecorded(items: list[ComplianceItem]) -> list[ComplianceItem]:
    """Reported separately from outstanding: an unknown is not a pass, and it
    is not a breach either."""
    return [item for item in items if item.status is ComplianceStatus.NOT_RECORDED]
