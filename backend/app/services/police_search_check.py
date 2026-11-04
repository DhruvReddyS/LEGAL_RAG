"""Does the record of a search satisfy the BNSS provisions that govern it.

This reads a record. It does not rule on whether a search was lawful: only a court
does that, and a defect here may be curable or immaterial. So there is no "legal"
verdict at any level, only what the record shows against each provision, in four
states, and "cannot be determined" stays that way until somebody records the answer.

Every check names its sub-section, read from the Sanhita in the corpus.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

__all__ = ["CHECK_QUESTIONS", "CheckVerdict", "SearchCheck", "SearchRecord", "evaluate_search", "overall"]


class CheckVerdict(StrEnum):
    MET = "met"
    NOT_MET = "not_met"
    CANNOT_BE_DETERMINED = "cannot_be_determined"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class SearchRecord:
    basis: str = "unknown"  # warrant | section_185 | unknown
    searched_at: datetime | None = None
    grounds_recorded_at: datetime | None = None
    record_sent_to_magistrate_at: datetime | None = None
    recording_forwarded_at: datetime | None = None
    witness_count: int | None = None
    answers: dict[str, str] | None = None


@dataclass(frozen=True)
class SearchCheck:
    key: str
    requirement: str
    provision: str
    verdict: CheckVerdict
    detail: str


@dataclass(frozen=True)
class _Question:
    key: str
    requirement: str
    provision: str
    # warrant | section_185 | any
    applies_to: str = "any"
    # A key whose "yes" answer brings this into play, for conditional rows.
    only_if: str = ""


# Questions the officer answers yes / no / unknown. Rows computed from recorded
# times are in evaluate_search, so a date on file cannot be contradicted by a tick.
_QUESTIONS: tuple[_Question, ...] = (
    _Question(
        "warrant_produced",
        "The warrant was produced on demand before entering the closed place.",
        "BNSS s.103(1)",
        "warrant",
        "place_was_closed",
    ),
    _Question(
        "reasonable_grounds",
        "The officer had reasonable grounds to believe the thing was necessary for the "
        "investigation and could not otherwise be obtained without undue delay.",
        "BNSS s.185(1)",
        "section_185",
    ),
    _Question(
        "within_station_limits",
        "The place searched is within the limits of the officer's police station.",
        "BNSS s.185(1)",
        "section_185",
    ),
    _Question(
        "thing_specified",
        "The grounds in the case diary specify, so far as possible, the thing searched for.",
        "BNSS s.185(1)",
        "section_185",
    ),
    _Question(
        "conducted_in_person",
        "The officer conducted the search in person, if practicable.",
        "BNSS s.185(2)",
        "section_185",
    ),
    _Question(
        "delegation_reasons_and_order",
        "Where a subordinate searched: reasons were recorded in writing and a written "
        "order specifying the place and the thing was delivered.",
        "BNSS s.185(3)",
        "section_185",
        "delegated_to_subordinate",
    ),
    _Question(
        "witnesses_independent",
        "The witnesses were independent and respectable inhabitants of the locality, or "
        "of another locality because none there was available or willing.",
        "BNSS s.103(4)",
    ),
    _Question(
        "search_in_witnesses_presence",
        "The search was made in the presence of the witnesses.",
        "BNSS s.103(5)",
    ),
    _Question(
        "seizure_list_prepared",
        "A list was prepared of all things seized and the places where each was found.",
        "BNSS s.103(5)",
    ),
    _Question("seizure_list_signed", "The witnesses signed the list.", "BNSS s.103(5)"),
    _Question(
        "occupant_allowed_to_attend",
        "The occupant, or someone on the occupant's behalf, was permitted to attend.",
        "BNSS s.103(6)",
    ),
    _Question(
        "list_copy_to_occupant",
        "A copy of the signed list was delivered to the occupant or that person.",
        "BNSS s.103(6)",
    ),
    _Question(
        "person_list_copy",
        "A list of things taken from the person searched was prepared, and a copy delivered.",
        "BNSS s.103(7)",
        "any",
        "person_searched",
    ),
    _Question(
        "woman_searched_by_woman",
        "The woman was searched by another woman, with strict regard to decency.",
        "BNSS s.103(3)",
        "any",
        "woman_searched",
    ),
    _Question(
        "audio_video_recorded",
        "The search and seizure, including preparing and signing the list, were recorded "
        "by audio-video electronic means.",
        "BNSS s.105",
    ),
    _Question(
        "seizure_reported_to_magistrate",
        "The seizure was reported to the Magistrate having jurisdiction, forthwith.",
        "BNSS s.106(3)",
        "any",
        "seized_under_s106",
    ),
)

# The conditions, asked first so the list can show only what applies.
CHECK_QUESTIONS = {
    "conditions": [
        {"key": "place_was_closed", "question": "The place was closed when the officers arrived."},
        {"key": "delegated_to_subordinate", "question": "A subordinate made the search rather than the officer."},
        {"key": "person_searched", "question": "A person was searched, not only the place."},
        {"key": "woman_searched", "question": "A woman was searched."},
        {"key": "seized_under_s106", "question": "Property was seized on suspicion of an offence (s.106)."},
    ],
    "questions": [
        {
            "key": q.key,
            "requirement": q.requirement,
            "provision": q.provision,
            "applies_to": q.applies_to,
            "only_if": q.only_if,
        }
        for q in _QUESTIONS
    ],
}


def evaluate_search(record: SearchRecord, now: datetime) -> list[SearchCheck]:
    answers = record.answers or {}
    out: list[SearchCheck] = []

    if record.basis == "unknown":
        out.append(
            SearchCheck(
                "basis_recorded",
                "The record states whether the search was under a warrant or under s.185.",
                "BNSS s.185(1)",
                CheckVerdict.CANNOT_BE_DETERMINED,
                "The basis of the search is not recorded, so the s.185 requirements below "
                "cannot be applied or excluded.",
            )
        )

    def applies(question: _Question) -> bool | None:
        if question.applies_to == "any" or record.basis == question.applies_to:
            return True
        return None if record.basis == "unknown" else False

    for question in _QUESTIONS:
        applicable = applies(question)
        if applicable is False:
            continue
        if question.only_if:
            condition = answers.get(question.only_if, "unknown")
            if condition == "no":
                continue
            if condition != "yes":
                out.append(
                    SearchCheck(
                        question.key,
                        question.requirement,
                        question.provision,
                        CheckVerdict.CANNOT_BE_DETERMINED,
                        "Whether this applies is not recorded.",
                    )
                )
                continue
        answer = answers.get(question.key, "unknown")
        verdict = (
            CheckVerdict.CANNOT_BE_DETERMINED
            if applicable is None
            else {"yes": CheckVerdict.MET, "no": CheckVerdict.NOT_MET}.get(
                answer, CheckVerdict.CANNOT_BE_DETERMINED
            )
        )
        detail = {
            CheckVerdict.MET: "Recorded as done.",
            CheckVerdict.NOT_MET: "Recorded as not done.",
            CheckVerdict.CANNOT_BE_DETERMINED: "Not recorded either way.",
        }[verdict]
        if applicable is None:
            detail = "Applies only if the search was under s.185, and the basis is not recorded."
        out.append(SearchCheck(question.key, question.requirement, question.provision, verdict, detail))

    # ---- Computed from what is on the record, not asked.
    if record.witness_count is None:
        out.append(
            SearchCheck(
                "two_or_more_witnesses",
                "Two or more independent witnesses were called to attend.",
                "BNSS s.103(4)",
                CheckVerdict.CANNOT_BE_DETERMINED,
                "The number of witnesses is not recorded.",
            )
        )
    else:
        enough = record.witness_count >= 2
        out.append(
            SearchCheck(
                "two_or_more_witnesses",
                "Two or more independent witnesses were called to attend.",
                "BNSS s.103(4)",
                CheckVerdict.MET if enough else CheckVerdict.NOT_MET,
                f"{record.witness_count} witness(es) recorded.",
            )
        )

    if record.basis != "warrant":
        out.append(_grounds_before_search(record))
        out.append(_copies_within_48_hours(record, now))

    if record.recording_forwarded_at is not None:
        out.append(
            SearchCheck(
                "recording_forwarded",
                "The recording was forwarded without delay to the District Magistrate, "
                "Sub-divisional Magistrate or Judicial Magistrate of the first class.",
                "BNSS s.105",
                CheckVerdict.MET,
                "A forwarding date is recorded. The section says without delay and sets no "
                "fixed period, so whether the interval was acceptable is not decided here.",
            )
        )
    else:
        out.append(
            SearchCheck(
                "recording_forwarded",
                "The recording was forwarded without delay to the District Magistrate, "
                "Sub-divisional Magistrate or Judicial Magistrate of the first class.",
                "BNSS s.105",
                CheckVerdict.CANNOT_BE_DETERMINED,
                "No forwarding date is recorded.",
            )
        )
    return out


def _grounds_before_search(record: SearchRecord) -> SearchCheck:
    key = "grounds_recorded_before_search"
    requirement = "The grounds of belief were recorded in writing in the case diary before the search."
    provision = "BNSS s.185(1)"
    if record.grounds_recorded_at is None or record.searched_at is None:
        verdict, detail = (
            CheckVerdict.CANNOT_BE_DETERMINED,
            "Both the time the grounds were recorded and the time of the search are needed.",
        )
    elif record.grounds_recorded_at <= record.searched_at:
        verdict, detail = CheckVerdict.MET, "The recorded times put the grounds before the search."
    else:
        verdict, detail = (
            CheckVerdict.NOT_MET,
            "The recorded times put the grounds after the search began.",
        )
    if record.basis == "unknown":
        verdict, detail = (
            CheckVerdict.CANNOT_BE_DETERMINED,
            "Applies only if the search was under s.185, and the basis is not recorded.",
        )
    return SearchCheck(key, requirement, provision, verdict, detail)


def _copies_within_48_hours(record: SearchRecord, now: datetime) -> SearchCheck:
    key = "record_copies_within_48_hours"
    requirement = (
        "Copies of the s.185 record went to the nearest Magistrate empowered to take "
        "cognizance, forthwith and not later than forty-eight hours."
    )
    provision = "BNSS s.185(5)"
    limit = timedelta(hours=48)
    if record.basis == "unknown":
        return SearchCheck(
            key, requirement, provision, CheckVerdict.CANNOT_BE_DETERMINED,
            "Applies only if the search was under s.185, and the basis is not recorded.",
        )
    if record.grounds_recorded_at is None:
        return SearchCheck(
            key, requirement, provision, CheckVerdict.CANNOT_BE_DETERMINED,
            "The time the grounds were recorded is not on the record, so the limit cannot be computed.",
        )
    if record.record_sent_to_magistrate_at is None:
        passed = now - record.grounds_recorded_at > limit
        return SearchCheck(
            key, requirement, provision, CheckVerdict.CANNOT_BE_DETERMINED,
            "The forty-eight hours have passed and no sending date is recorded."
            if passed
            else "No sending date is recorded yet, and the forty-eight hours are still running.",
        )
    if record.record_sent_to_magistrate_at - record.grounds_recorded_at <= limit:
        return SearchCheck(key, requirement, provision, CheckVerdict.MET, "Recorded as sent within forty-eight hours.")
    return SearchCheck(key, requirement, provision, CheckVerdict.NOT_MET, "Recorded as sent after forty-eight hours.")


def overall(checks: list[SearchCheck]) -> dict[str, object]:
    """What the record shows. Deliberately not a verdict on legality."""
    counts = {verdict.value: 0 for verdict in CheckVerdict}
    for check in checks:
        counts[check.verdict.value] += 1
    if counts[CheckVerdict.NOT_MET.value]:
        finding = "defect_on_record"
    elif counts[CheckVerdict.CANNOT_BE_DETERMINED.value]:
        finding = "incomplete_record"
    else:
        finding = "no_defect_on_record"
    return {"finding": finding, "counts": counts}
