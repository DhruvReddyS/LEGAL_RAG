"""Working drafts of the documents an investigation produces.

Deterministic templates filled from what is on record for the case. No model writes
them, so nothing can appear in a draft that the officer or the record did not supply.
Where a value is missing the draft says so in brackets and lists it, rather than
leaving a blank that reads as finished. Every draft opens and closes by saying it has
not been signed, issued or filed, and the status stored with it is "draft".

The formats are not prescribed forms. s.193(3)(i) leaves the report's form to State
rules, and those are not in the corpus, so the chargesheet skeleton follows the heads
of the section and says that the State form governs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from app.core.india_time import india_moment_text

__all__ = ["DRAFT_TYPES", "DraftContext", "RenderedDraft", "render_draft"]

DISCLAIMER = (
    "DRAFT for the investigating officer's review. It has not been signed, issued or "
    "filed. Verify every fact against the record and the State's prescribed form before "
    "use. Corpusil gives legal information and does not replace the officer's judgment "
    "or a prosecutor's advice."
)
BANNER = "DRAFT - NOT SIGNED - NOT ISSUED - NOT FILED"


@dataclass
class DraftContext:
    case_title: str
    officer_name: str
    facts: dict = field(default_factory=dict)
    evidence: list[dict] = field(default_factory=list)
    witnesses: list[dict] = field(default_factory=list)
    searches: list[dict] = field(default_factory=list)
    remand: dict = field(default_factory=dict)
    diary: list[dict] = field(default_factory=list)
    offences: list[str] = field(default_factory=list)
    now: datetime | None = None


@dataclass(frozen=True)
class RenderedDraft:
    draft_type: str
    title: str
    rendered_text: str
    missing_fields: list[str]
    provisions: list[str]
    disclaimer: str = DISCLAIMER


class _Filler:
    def __init__(self, inputs: dict) -> None:
        self.inputs = inputs
        self.missing: list[str] = []

    def __call__(self, key: str, label: str, value: object = None) -> str:
        given = value if value not in (None, "") else self.inputs.get(key)
        if given in (None, ""):
            if label not in self.missing:
                self.missing.append(label)
            return f"[NOT RECORDED: {label}]"
        return str(given).strip()


def _when(value: object) -> str | None:
    if isinstance(value, datetime):
        return india_moment_text(value)
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    return str(value) if value else None


def _lines(*parts: str) -> str:
    return "\n".join(parts)


def _section_35_3(ctx: DraftContext, fill: _Filler) -> tuple[str, list[str]]:
    body = _lines(
        "NOTICE OF APPEARANCE",
        "Under section 35(3) of the Bharatiya Nagarik Suraksha Sanhita, 2023",
        "",
        f"Case: {ctx.case_title}",
        f"Offence under section(s): {fill('offence_sections', 'offence sections', ', '.join(ctx.offences) or None)}",
        "",
        f"To: {fill('person_name', 'name of the person noticed')}",
        f"Address: {fill('person_address', 'address of the person noticed')}",
        "",
        f"A reasonable complaint has been made, or credible information received, or a reasonable "
        f"suspicion exists, that you have committed a cognizable offence: "
        f"{fill('grounds', 'substance of the complaint or information')}.",
        "",
        f"You are directed to appear before {fill('appear_before', 'officer to appear before', ctx.officer_name)} "
        f"at {fill('appear_at', 'place of appearance')} on {fill('appear_on', 'date and time of appearance')}.",
        "",
        "Under section 35(4) it is your duty to comply with the terms of this notice.",
        "Under section 35(5), while you comply and continue to comply, you shall not be arrested in "
        "respect of the offence referred to in this notice unless, for reasons to be recorded, the "
        "police officer is of the opinion that you ought to be arrested.",
        "Under section 35(6), if you fail to comply with the terms of this notice or are unwilling to "
        "identify yourself, the police officer may, subject to any order of a competent Court, arrest "
        "you for the offence mentioned in this notice.",
        "",
        f"Issued by: {fill('issued_by', 'issuing officer', ctx.officer_name)}",
        "Rank and police station: " + fill("rank_and_station", "rank and police station"),
        "Date: " + fill("issue_date", "date of issue"),
    )
    return body, ["BNSS s.35(3)", "BNSS s.35(4)", "BNSS s.35(5)", "BNSS s.35(6)"]


def _section_94(ctx: DraftContext, fill: _Filler) -> tuple[str, list[str]]:
    body = _lines(
        "WRITTEN ORDER TO PRODUCE",
        "Under section 94(1) of the Bharatiya Nagarik Suraksha Sanhita, 2023",
        "",
        f"Case: {ctx.case_title}",
        "",
        f"To: {fill('person_name', 'person in possession or power')}",
        f"Address: {fill('person_address', 'address of that person')}",
        "",
        "The officer in charge of this police station considers that the production of the following "
        f"is necessary or desirable for the purposes of this investigation: "
        f"{fill('thing_to_produce', 'document, communication, device or other thing to produce')}.",
        "",
        f"Why it is believed to be in your possession or power: {fill('basis', 'basis for that belief')}.",
        "",
        f"You are required to attend and produce it, or to produce it, at "
        f"{fill('produce_at', 'place of production')} on {fill('produce_on', 'date and time of production')}.",
        "",
        "Under section 94(2), if you are required merely to produce it, you comply by causing it to be "
        "produced instead of attending personally.",
        "",
        f"Officer in charge of the police station: {fill('issued_by', 'officer in charge', ctx.officer_name)}",
        "Police station: " + fill("station", "police station"),
        "Date: " + fill("issue_date", "date of issue"),
        "",
        "For the officer, not for service: section 94(1) gives this power to the officer in charge of a "
        "police station. Section 94(3) leaves sections 129 and 130 of the Bharatiya Sakshya Adhiniyam, "
        "2023 and the Bankers' Books Evidence Act, 1891 unaffected, and the section does not apply to a "
        "letter, postcard, document, parcel or thing in the custody of the postal authority.",
    )
    return body, ["BNSS s.94(1)", "BNSS s.94(2)", "BNSS s.94(3)"]


def _seizure_memo(ctx: DraftContext, fill: _Filler) -> tuple[str, list[str]]:
    search_id = fill.inputs.get("search_id")
    search = next((s for s in ctx.searches if str(s.get("id")) == str(search_id)), None)
    items = ctx.evidence
    if search is not None:
        items = [e for e in ctx.evidence if str(e.get("search_id")) == str(search["id"])]
    item_lines = [
        f"  {i + 1}. {item.get('exhibit_label')}: {item.get('description')}. Found at: "
        f"{item.get('seized_from') or '[NOT RECORDED: place found]'}."
        for i, item in enumerate(items)
    ] or ["  [NOT RECORDED: nothing is on the inventory for this search]"]
    if not items:
        fill.missing.append("things seized")
    witnesses = [w for w in ctx.witnesses if w.get("category") == "search_witness"]
    witness_lines = [f"  {i + 1}. {w.get('name')}" for i, w in enumerate(witnesses)] or [
        "  [NOT RECORDED: witnesses to the search]"
    ]
    if not witnesses:
        fill.missing.append("witnesses to the search")
    body = _lines(
        "SEIZURE MEMO / LIST OF THINGS SEIZED",
        "Sections 103 and 105 of the Bharatiya Nagarik Suraksha Sanhita, 2023",
        "",
        f"Case: {ctx.case_title}",
        f"Place searched: {fill('place', 'place searched', search.get('place') if search else None)}",
        f"Date and time: {fill('searched_at', 'date and time of search', _when(search.get('searched_at')) if search else None)}",
        f"Basis: {fill('basis', 'basis of the search (warrant or section 185)', search.get('basis') if search and search.get('basis') != 'unknown' else None)}",
        f"Occupant: {fill('occupant', 'occupant or person attending on behalf')}",
        "",
        "Witnesses called under section 103(4):",
        *witness_lines,
        "",
        "Things seized, and the place in which each was found (section 103(5)):",
        *item_lines,
        "",
        "Signature of each witness: ______________________",
        f"Prepared by: {fill('officer', 'officer preparing the list', ctx.officer_name)}",
        "",
        "To record before this is used:",
        "  - Audio-video recording of the search and of preparing and signing this list (section 105): "
        + fill("recording_reference", "recording reference"),
        "  - Recording forwarded to the Magistrate (section 105): "
        + fill("recording_forwarded", "date the recording was forwarded", _when(search.get("recording_forwarded_at")) if search else None),
        "  - Copy delivered to the occupant (section 103(6)): " + fill("copy_delivered", "copy delivered to the occupant"),
        "  - Seizure reported to the Magistrate where section 106(3) applies: " + fill("seizure_reported", "seizure report to the Magistrate"),
    )
    return body, ["BNSS s.103(4)", "BNSS s.103(5)", "BNSS s.103(6)", "BNSS s.105", "BNSS s.106(3)"]


def _case_diary(ctx: DraftContext, fill: _Filler) -> tuple[str, list[str]]:
    page = fill.inputs.get("diary_page")
    entry = next((d for d in ctx.diary if str(d.get("page_no")) == str(page)), None)
    get = (lambda key: entry.get(key)) if entry else (lambda key: None)
    next_page = (max((d.get("page_no") or 0 for d in ctx.diary), default=0)) + 1
    body = _lines(
        "CASE DIARY ENTRY",
        "Section 192 of the Bharatiya Nagarik Suraksha Sanhita, 2023",
        "",
        f"Case: {ctx.case_title}",
        f"Page: {get('page_no') or next_page} (section 192(3): a volume, duly paginated)",
        f"Date: {fill('entry_date', 'date of the entry', _when(get('entry_date')))}",
        "",
        f"Time the information reached the officer: {fill('information_reached_at', 'time the information reached the officer', _when(get('information_reached_at')))}",
        f"Time the investigation began: {fill('began_at', 'time the investigation began', _when(get('began_at')))}",
        f"Time the investigation closed: {fill('closed_at', 'time the investigation closed', _when(get('closed_at')))}",
        f"Place or places visited: {fill('places_visited', 'places visited', get('places_visited'))}",
        "",
        "Statement of the circumstances ascertained through the investigation:",
        fill("circumstances", "circumstances ascertained", get("circumstances")),
        "",
        "Statements under section 180 inserted in this diary (section 192(2)):",
        fill("statements_inserted", "statements inserted", get("statements_inserted")),
        "",
        f"Officer: {fill('officer', 'officer making the entry', ctx.officer_name)}",
    )
    return body, ["BNSS s.192(1)", "BNSS s.192(2)", "BNSS s.192(3)"]


def _remand(ctx: DraftContext, fill: _Filler) -> tuple[str, list[str]]:
    facts = ctx.facts
    remand = ctx.remand
    custody = fill("custody_sought", "custody sought (police or judicial)")
    used = remand.get("police_days_used")
    left = remand.get("police_days_left")
    window = remand.get("police_custody_window_ends")
    body = _lines(
        "APPLICATION FOR REMAND",
        "Under section 187 of the Bharatiya Nagarik Suraksha Sanhita, 2023",
        "",
        f"Before: {fill('magistrate', 'Magistrate')}",
        f"Case: {ctx.case_title}",
        f"Accused: {fill('accused_name', 'name of the accused')}",
        f"Offence under section(s): {fill('offence_sections', 'offence sections', ', '.join(ctx.offences) or None)}",
        f"Arrested on: {fill('arrested_at', 'time of arrest', _when(facts.get('arrested_at')))}",
        f"First remand: {_when(facts.get('first_remand_at')) or 'None recorded. If this is the first remand, say so.'}",
        "",
        "The investigation cannot be completed within the twenty-four hours fixed by section 58, and "
        "there are grounds for believing that the accusation or information is well-founded (section 187(1)):",
        fill("grounds", "grounds for believing the accusation well-founded"),
        "",
        f"Custody sought: {custody} for {fill('days_sought', 'days sought')} day(s).",
        f"Why further detention is necessary: {fill('why_necessary', 'why further detention is necessary')}",
        "",
        "Enclosed: a copy of the entries in the case diary relating to the case (section 187(1)).",
        "The accused is produced in person, as section 187(4) requires for the first production and "
        "for every remand to police custody. Judicial custody may be extended by audio-video electronic means.",
        "",
        "From the record of custody so far, for the officer to check against the orders:",
        f"  - Police custody used: {used if used is not None else 'not recorded'} day(s), of the fifteen in section 187(2). Remaining: {left if left is not None else 'not recorded'}.",
        f"  - Initial period within which police custody may fall ends on: {_when(window) or 'cannot be determined: ' + (remand.get('undetermined_because') or 'not recorded')}.",
        "",
        f"Applicant: {fill('officer', 'applicant officer', ctx.officer_name)}",
        "Rank (not below sub-inspector, section 187(1)): " + fill("rank", "rank"),
        "Date: " + fill("application_date", "date of application"),
    )
    return body, ["BNSS s.187(1)", "BNSS s.187(2)", "BNSS s.187(3)", "BNSS s.187(4)", "BNSS s.58"]


def _chargesheet(ctx: DraftContext, fill: _Filler) -> tuple[str, list[str]]:
    facts = ctx.facts
    # Clause (h) is BNS ss.64-68, 70, 71 only; a POCSO case on s.193(2) is not in it.
    listed = bool(facts.get("clause_h_applies")) or bool(facts.get("is_rape_or_attempt"))
    electronic = [e for e in ctx.evidence if e.get("category") == "electronic"]
    witnesses = [w for w in ctx.witnesses if w.get("status") not in ("dropped", "entered_in_error")]
    provisions = [
        "BNSS s.193(3)(i)",
        "BNSS s.193(6)(a)",
        "BNSS s.193(6)(b)",
        "BNSS s.193(8)",
    ]
    witness_lines = [
        f"  {i + 1}. {w.get('name')} ({str(w.get('category')).replace('_', ' ')}). Statement: "
        f"{_when(w.get('statement_recorded_at')) or '[NOT RECORDED]'}."
        for i, w in enumerate(witnesses)
    ] or ["  [NOT RECORDED: nobody is on the witness tracker]"]
    if not witnesses:
        fill.missing.append("persons acquainted with the circumstances")
    evidence_lines = [
        f"  {item.get('exhibit_label')}: {item.get('description')}"
        for item in ctx.evidence
        if item.get("status") != "entered_in_error"
    ] or ["  [NOT RECORDED: nothing is on the inventory]"]
    blocks = [
        "REPORT OF THE POLICE OFFICER ON COMPLETION OF INVESTIGATION: SKELETON",
        "Section 193(3) of the Bharatiya Nagarik Suraksha Sanhita, 2023",
        "The heads below follow section 193(3)(i). The State Government prescribes the form by rules, "
        "and that form governs.",
        "",
        f"To: {fill('magistrate', 'Magistrate empowered to take cognizance')}",
        f"Case: {ctx.case_title}",
        "",
        f"(a) Names of the parties: {fill('parties', 'names of the parties')}",
        f"(b) Nature of the information: {fill('nature_of_information', 'nature of the information')}",
        "(c) Persons who appear to be acquainted with the circumstances of the case:",
        *witness_lines,
        f"(d) Whether any offence appears to have been committed and, if so, by whom: {fill('offence_finding', 'whether an offence appears committed and by whom', None)}",
        f"     Offence section(s) under assessment: {', '.join(ctx.offences) or '[NOT RECORDED]'}",
        f"(e) Whether the accused has been arrested: {fill('accused_arrested', 'whether the accused has been arrested', 'Yes, on ' + _when(facts['arrested_at']) if facts.get('arrested_at') else None)}",
        f"(f) Whether the accused has been released on bond or bail bond: {fill('released_on_bond', 'whether released on bond or bail bond')}",
        f"(g) Whether the accused has been forwarded in custody under section 190: {fill('forwarded_in_custody', 'whether forwarded in custody')}",
    ]
    if listed:
        blocks.append(
            f"(h) Whether the report of medical examination of the woman has been attached: "
            f"{fill('medical_report', 'whether the medical examination report is attached')}"
        )
        provisions.append("BNSS s.193(3)(i)(h)")
    if electronic:
        blocks.append("(i) Sequence of custody in case of electronic device:")
        for item in electronic:
            hops = item.get("custody_events") or []
            chain = "; ".join(
                f"{_when(h.get('occurred_at'))}: {h.get('from_person')} to {h.get('to_person')}" for h in hops
            )
            blocks.append(
                f"  {item.get('exhibit_label')}: seized by {item.get('seized_by') or '[NOT RECORDED]'}"
                f" on {_when(item.get('seized_at')) or '[NOT RECORDED]'}."
                f" {chain or 'No hand-over is on record.'}"
            )
        provisions.append("BNSS s.193(3)(i)(i)")
    blocks += [
        "",
        "Enclosures under section 193(6), for a case to which section 190 applies:",
        "  (a) All documents or relevant extracts on which the prosecution proposes to rely:",
        *evidence_lines,
        "  (b) Statements under section 180 of all persons the prosecution proposes to examine.",
        "",
        "Copies under section 193(8), duly indexed, for supply to the accused under section 230.",
        "",
        f"Officer in charge: {fill('officer', 'officer in charge', ctx.officer_name)}",
        "Date: " + fill("report_date", "date of report"),
    ]
    return "\n".join(blocks), provisions


DRAFT_TYPES = {
    "s35_3_notice": ("Notice of appearance, s.35(3)", _section_35_3),
    "s94_production_order": ("Order to produce, s.94", _section_94),
    "seizure_memo": ("Seizure memo", _seizure_memo),
    "case_diary_entry": ("Case diary entry, s.192", _case_diary),
    "remand_application": ("Remand application, s.187", _remand),
    "chargesheet_skeleton": ("Chargesheet skeleton, s.193(3)", _chargesheet),
}


def render_draft(draft_type: str, ctx: DraftContext, inputs: dict | None = None) -> RenderedDraft:
    title, builder = DRAFT_TYPES[draft_type]
    fill = _Filler(inputs or {})
    body, provisions = builder(ctx, fill)
    text = "\n".join((BANNER, "", body, "", "---", DISCLAIMER, "", BANNER))
    return RenderedDraft(
        draft_type=draft_type,
        title=title,
        rendered_text=text,
        missing_fields=fill.missing,
        provisions=provisions,
    )
