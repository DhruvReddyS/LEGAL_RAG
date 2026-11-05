"""The printable case file.

A page assembled from the record and nothing else, escaped at every interpolation:
exhibit descriptions and witness names are free text typed by a person, and this HTML
is opened in a browser. Its scripts cannot run where the app displays it, and it does
not rely on that.

It says what it is at the top and the bottom: a compilation for review. Unknowns are
printed as unknowns, and drafts carry the word DRAFT in the section heading and on
each document.
"""

from __future__ import annotations

from datetime import date, datetime
from html import escape

from app.core.india_time import india_moment_text

__all__ = ["render_case_file"]

NOTE = (
    "Compiled from the investigation record for review. This is not a filed document, an "
    "official form or a certified copy. Items shown as not recorded are not findings "
    "either way. Check it against the original record before relying on it."
)

_CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
html, body { margin: 0; background: #fff; color: #1b1c1b; }
body { font: 11pt/1.45 Georgia, 'Times New Roman', serif; padding: 24px; max-width: 920px; margin: auto; }
h1 { font-size: 18pt; margin: 0 0 4px; }
h2 { font-size: 13pt; margin: 26px 0 8px; padding-bottom: 4px; border-bottom: 1.5px solid #1b1c1b; break-after: avoid; }
h3 { font-size: 11pt; margin: 14px 0 4px; break-after: avoid; }
p { margin: 4px 0; }
.note { border: 1px solid #1b1c1b; padding: 8px 10px; font-size: 9.5pt; margin: 10px 0 16px; }
table { width: 100%; border-collapse: collapse; font-size: 9.5pt; margin: 6px 0 12px; }
th, td { border: 1px solid #8a8d8a; padding: 4px 6px; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
th { background: #eeefed; font-weight: 600; }
tr { break-inside: avoid; }
thead { display: table-header-group; }
.state { font-weight: 700; }
.muted { color: #555; font-size: 9.5pt; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font: 9.5pt/1.45 'Courier New', monospace; border: 1px dashed #1b1c1b; padding: 8px; }
.draft { break-before: page; }
.draft:first-of-type { break-before: auto; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 2px 12px; font-size: 10pt; margin: 4px 0; }
dt { font-weight: 600; } dd { margin: 0; overflow-wrap: anywhere; }
"""


def _text(value: object) -> str:
    if value is None or value == "":
        return "Not recorded"
    if isinstance(value, datetime):
        return india_moment_text(value)
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    return str(value)


def _cell(value: object) -> str:
    return escape(_text(value))


def _table(headers: list[str], rows: list[list[object]], empty: str) -> str:
    if not rows:
        return f'<p class="muted">{escape(empty)}</p>'
    head = "".join(f'<th scope="col">{escape(h)}</th>' for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{_cell(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _word(value: str) -> str:
    return value.replace("_", " ")


def render_case_file(data: dict) -> str:
    """`data` is plain values; see the router for its shape."""
    case = data["case"]
    parts: list[str] = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        f"<title>{escape(case['title'])}: case file</title><style>{_CSS}</style></head><body>",
        f"<h1>{escape(case['title'])}</h1>",
        f"<p class='muted'>Case file compiled {_cell(data['generated_at'])} by {_cell(data['officer_name'])}. "
        f"Status: {_cell(case['status'])}. Opened {_cell(case['created_at'])}.</p>",
        f"<div class='note'>{escape(NOTE)}</div>",
    ]

    facts = data.get("facts") or {}
    parts.append("<h2>1. Recorded facts</h2>")
    if not facts:
        parts.append("<p class='muted'>No investigation dates have been recorded for this case.</p>")
    else:
        parts.append("<dl>")
        for label, value in (
            ("Information recorded", facts.get("information_recorded_at")),
            ("Arrest", facts.get("arrested_at")),
            ("Arrest type", {True: "Under warrant", False: "Without warrant"}.get(facts.get("arrested_under_warrant"))),
            ("First remand", facts.get("first_remand_at")),
            ("Accused produced or appeared", facts.get("accused_produced_at")),
            ("Police report forwarded", facts.get("police_report_forwarded_at")),
            ("Preliminary enquiry begun", facts.get("preliminary_enquiry_started_at")),
            ("Death occurred", facts.get("death_occurred_at")),
            ("Offence gravity", _word(str(facts.get("gravity") or "unknown"))),
        ):
            parts.append(f"<dt>{escape(label)}</dt><dd>{_cell(value)}</dd>")
        parts.append("</dl>")

    parts.append("<h2>2. Statutory timeline</h2>")
    parts.append(
        _table(
            ["Obligation", "Provision", "Due", "State", "Why"],
            [
                [r["obligation"], r["provision"], r["due_at"], _word(r["state"]).upper(), r["state_reason"]]
                for r in data.get("deadlines", [])
            ],
            "No deadline follows from the dates recorded. That is not a finding that none applies.",
        )
    )

    parts.append("<h2>3. Compliance record</h2>")
    for action in data.get("compliance", []):
        parts.append(f"<h3>{escape(_word(action['action']).capitalize())}</h3>")
        parts.append(
            _table(
                ["Requirement", "Provision", "Status", "Date", "Evidence"],
                [
                    [i["requirement"], i["provision"], _word(i["status"]).upper(), i.get("occurred_at"), i.get("evidence")]
                    for i in action["items"]
                ],
                "No requirement listed.",
            )
        )

    parts.append("<h2>4. Evidence inventory and chain of custody</h2>")
    items = data.get("evidence", [])
    if not items:
        parts.append("<p class='muted'>Nothing is on the inventory.</p>")
    for item in items:
        parts.append(f"<h3>{escape(item['exhibit_label'])}: {escape(item['description'])}</h3>")
        parts.append(
            f"<p>Category {_cell(item['category'])}. Seized by {_cell(item.get('seized_by'))} on "
            f"{_cell(item.get('seized_at'))} from {_cell(item.get('seized_from'))}. Status "
            f"{_cell(_word(item.get('status') or ''))}. Held at {_cell(item.get('storage_location'))}.</p>"
        )
        if item.get("category") == "electronic":
            parts.append(
                f"<p>Hash {_cell(item.get('digital_hash'))}. BSA s.63(4) certificate: "
                f"{_cell(_word(item.get('certificate_s63') or 'unknown'))}.</p>"
            )
        chain = item.get("chain") or {}
        parts.append(
            f"<p><span class='state'>Chain: {escape(_word(chain.get('state', 'cannot_be_determined')).upper())}.</span> "
            f"Last recorded holder: {_cell(chain.get('current_holder'))}.</p>"
        )
        for issue in chain.get("issues", []):
            parts.append(f"<p>{escape(issue)}</p>")
        parts.append(
            _table(
                ["When", "From", "To", "Purpose", "Place"],
                [
                    [h["occurred_at"], h["from_person"], h["to_person"], h.get("purpose"), h.get("place")]
                    for h in item.get("custody_events", [])
                ],
                "No hand-over is on record.",
            )
        )

    parts.append("<h2>5. Witnesses</h2>")
    witness_headers = ["Name", "Category", "Status", "Statement (s.180)", "Before a Magistrate (s.183)", "Bond (s.190(2))"]
    include_contact = data.get("include_witness_contact")
    if include_contact:
        witness_headers.insert(1, "Contact")
    parts.append(
        _table(
            witness_headers,
            [
                [
                    *([w["name"], w.get("contact")] if include_contact else [w["name"]]),
                    _word(w["category"]),
                    _word(w["status"]),
                    w.get("statement_recorded_at"),
                    w.get("magistrate_statement_at"),
                    w.get("bond_executed_at"),
                ]
                for w in data.get("witnesses", [])
            ],
            "Nobody is on the witness tracker.",
        )
    )
    if not include_contact and data.get("witnesses"):
        parts.append("<p class='muted'>Witness contact details are left out of this copy.</p>")

    parts.append("<h2>6. Searches</h2>")
    searches = data.get("searches", [])
    if not searches:
        parts.append("<p class='muted'>No search is on record.</p>")
    for search in searches:
        parts.append(
            f"<h3>{escape(search['place'])}</h3><p>Basis {_cell(_word(search.get('basis') or 'unknown'))}. "
            f"Searched {_cell(search.get('searched_at'))}. Record: "
            f"<span class='state'>{escape(_word(search['finding']).upper())}</span>.</p>"
        )
        parts.append(
            _table(
                ["Requirement", "Provision", "Record shows"],
                [[c["requirement"], c["provision"], _word(c["verdict"]).upper()] for c in search["checks"]],
                "No checks.",
            )
        )

    parts.append("<h2>7. Offence elements, as assessed by the investigating officer</h2>")
    offences = data.get("offences", [])
    if not offences:
        parts.append("<p class='muted'>No offence has been assessed.</p>")
    for offence in offences:
        parts.append(
            f"<h3>{escape(offence['title'])} ({escape(offence['provision'])}): "
            f"{escape(_word(offence['finding']).upper())}</h3>"
        )
        parts.append(
            _table(
                ["Element", "Provision", "Assessment", "Note"],
                [[e["element"], e["provision"], _word(e["state"]).upper(), e.get("note")] for e in offence["elements"]],
                "No elements.",
            )
        )

    parts.append("<h2>8. Remand and case diary</h2>")
    remand = data.get("remand") or {}
    parts.append(
        f"<p>Police custody on record: {_cell(remand.get('police_days_used'))} day(s) of fifteen (BNSS s.187(2)). "
        f"Judicial custody on record: {_cell(remand.get('judicial_days'))} day(s).</p>"
    )
    parts.append(
        _table(
            ["Page", "Date", "Began", "Closed", "Places", "Circumstances"],
            [
                [d["page_no"], d["entry_date"], d.get("began_at"), d.get("closed_at"), d.get("places_visited"), d["circumstances"]]
                for d in data.get("diary", [])
            ],
            "No diary entry is on record.",
        )
    )

    parts.append("<h2>9. Drafts (not signed, not issued, not filed)</h2>")
    drafts = data.get("drafts", [])
    if not drafts:
        parts.append("<p class='muted'>No draft is included.</p>")
    for draft in drafts:
        parts.append(
            f"<section class='draft'><h3>DRAFT: {escape(draft['title'])}, version {escape(str(draft['version']))}</h3>"
            f"<pre>{escape(draft['rendered_text'])}</pre></section>"
        )

    parts.append(f"<div class='note'>{escape(NOTE)}</div></body></html>")
    return "".join(parts)
