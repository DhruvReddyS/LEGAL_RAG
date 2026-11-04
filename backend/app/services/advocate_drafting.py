"""The advocate's drafting library: forms assembled by code, grounds verified.

The form of each document, its statutory anchor and its prayer are fixed here.
The advocate's facts are shown as instructions, not findings. Grounds come from
the model only after passing the claim check, and each inserted authority goes
through `authority_check`, as does the finished draft, so a repealed provision
can't sit in a petition unflagged.

Anything not known stays visibly `[INFORMATION REQUIRED]`. A draft is a draft.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.agents.advocate_agents import propose_verified_grounds
from app.agents.drafting_agent import authority_currency_note
from app.schemas.documents import DraftAuthority
from app.services.advocate_provisions import PROVISIONS, provision_sources
from app.services.advocate_sources import Evidence, gather_evidence
from app.services.authority_check import check_authorities
from app.services.llm import OllamaClient
from app.services.retrieval import HybridRetrievalService

DRAFT_DISCLAIMER = (
    "DRAFT FOR REVIEW. Not a filed document and not legal advice. The facts are as instructed and "
    "unverified. Check every fact, date, party, forum and authority, and the Court's own format and "
    "rules, before filing."
)
REQUIRED = "[INFORMATION REQUIRED]"


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    required: bool = True
    long: bool = False
    options: tuple[tuple[str, str], ...] = ()
    kind: str = "text"


@dataclass(frozen=True)
class DraftTemplate:
    key: str
    title: str
    description: str
    fields: tuple[Field, ...]
    uses_grounds: bool = True
    retrieval_hint: str = ""


_COMMON_COURT = (
    Field("court", "Court"),
    Field("case_reference", "Case or crime number and police station", required=False),
    Field("applicant", "Applicant / accused"),
    Field("respondent", "Respondent"),
)
_ADVOCATE = (Field("advocate", "Advocate's name", required=False), Field("place", "Place", required=False))

BAIL_ROUTES = {
    "regular_magistrate": ("regular bail", "bnss_480_1", "BNSS s.480"),
    "regular_superior": ("bail", "bnss_483_1", "BNSS s.483"),
    "anticipatory": ("anticipatory bail", "bnss_482_1", "BNSS s.482"),
    "default": ("bail on expiry of the period of detention", "bnss_187_3_release", "BNSS s.187(3)"),
    "undertrial": ("release of an undertrial prisoner", "bnss_479_1", "BNSS s.479"),
}

TEMPLATES: dict[str, DraftTemplate] = {
    "bail_application": DraftTemplate(
        "bail_application", "Bail application",
        "Regular, anticipatory, default or s.479. Check the route in the Bail tool first.",
        (
            Field("bail_route", "Route", options=(
                ("regular_magistrate", "Regular, before a Magistrate (BNSS s.480)"),
                ("regular_superior", "Before the Court of Session or High Court (BNSS s.483)"),
                ("anticipatory", "Anticipatory (BNSS s.482)"),
                ("default", "Default (BNSS s.187(3))"),
                ("undertrial", "Undertrial (BNSS s.479)"),
            )),
            *_COMMON_COURT,
            Field("offence", "Offence(s) alleged"),
            Field("custody", "Custody status and dates", required=False),
            Field("previous_applications", "Previous bail applications", required=False),
            *_ADVOCATE,
        ),
        retrieval_hint="bail grant of bail considerations",
    ),
    "discharge_application": DraftTemplate(
        "discharge_application", "Discharge application",
        "Sessions (BNSS s.250) or warrant cases on a police report (BNSS s.262). The sixty days is computed if you enter the date.",
        (
            Field("discharge_forum", "Forum", options=(
                ("sessions", "Court of Session (BNSS s.250)"),
                ("warrant", "Magistrate, warrant case on a police report (BNSS s.262)"),
            )),
            *_COMMON_COURT,
            Field("offence", "Offence(s) charged"),
            Field("trigger_date", "Date of commitment (s.250) or supply of copies (s.262)", required=False, kind="date"),
            *_ADVOCATE,
        ),
        retrieval_hint="discharge no sufficient ground for proceeding charge groundless",
    ),
    "quashing_petition": DraftTemplate(
        "quashing_petition", "Quashing petition",
        "Before the High Court under BNSS s.528.",
        (
            *_COMMON_COURT,
            Field("impugned", "FIR, chargesheet or proceeding to be quashed"),
            Field("offence", "Offence(s) alleged"),
            *_ADVOCATE,
        ),
        retrieval_hint="inherent powers High Court quashing abuse of process",
    ),
    "reply": DraftTemplate(
        "reply", "Reply / counter",
        "A para-wise reply to a filing, with verified grounds.",
        (
            *_COMMON_COURT,
            Field("responding_to", "Filing being answered"),
            Field("relief_opposed", "What is opposed, and why, in a line", required=False),
            *_ADVOCATE,
        ),
        retrieval_hint="",
    ),
    "legal_notice": DraftTemplate(
        "legal_notice", "Legal notice",
        "Notice before action. For a suit against the Government or a public officer, CPC s.80 is cited.",
        (
            Field("sender", "On behalf of"),
            Field("recipient", "To"),
            Field("recipient_address", "Recipient's address"),
            Field("demand", "What is demanded"),
            Field("compliance_period", "Period to comply"),
            Field("against_government", "Suit against Government or a public officer?", required=False, options=(
                ("no", "No"), ("yes", "Yes (CPC s.80)"),
            )),
            *_ADVOCATE,
        ),
        retrieval_hint="",
    ),
    "vakalatnama": DraftTemplate(
        "vakalatnama", "Vakalatnama",
        "Appointment in writing under CPC Order III rule 4. No model is involved.",
        (
            Field("court", "Court"),
            Field("case_reference", "Case number"),
            Field("client", "Client"),
            Field("client_role", "Client is"),
            Field("advocate", "Advocate's name"),
            Field("enrolment", "Enrolment number"),
            Field("address", "Advocate's address for service"),
            Field("place", "Place", required=False),
        ),
        uses_grounds=False,
    ),
    "written_submissions": DraftTemplate(
        "written_submissions", "Written submissions",
        "Headed submissions with verified grounds and authorities.",
        (
            *_COMMON_COURT,
            Field("stage", "Stage of the matter", required=False),
            Field("points_for_determination", "Points for determination", required=False, long=True),
            *_ADVOCATE,
        ),
        retrieval_hint="",
    ),
}


def template_catalogue() -> list[dict[str, Any]]:
    return [
        {
            "key": item.key,
            "title": item.title,
            "description": item.description,
            "uses_grounds": item.uses_grounds,
            "fields": [
                {
                    "name": field.name, "label": field.label, "required": field.required,
                    "long": field.long, "kind": field.kind,
                    "options": [{"value": value, "label": label} for value, label in field.options],
                }
                for field in item.fields
            ],
        }
        for item in TEMPLATES.values()
    ]


def _value(fields: dict[str, str], name: str) -> str:
    return (fields.get(name) or "").strip() or REQUIRED


def _statutory_keys(template: DraftTemplate, fields: dict[str, str]) -> tuple[list[str], str]:
    """Which pinned provisions this draft rests on, and how to name them."""
    if template.key == "bail_application":
        route = BAIL_ROUTES.get(fields.get("bail_route") or "")
        return ([route[1]], route[2]) if route else ([], REQUIRED)
    if template.key == "discharge_application":
        if fields.get("discharge_forum") == "sessions":
            return ["bnss_250_1", "bnss_250_2"], "BNSS s.250"
        if fields.get("discharge_forum") == "warrant":
            return ["bnss_262_1", "bnss_262_2"], "BNSS s.262"
        return [], REQUIRED
    if template.key == "quashing_petition":
        return ["bnss_528"], "BNSS s.528"
    if template.key == "vakalatnama":
        return ["cpc_order_3_rule_4"], "CPC, Order III, rule 4"
    if template.key == "legal_notice" and fields.get("against_government") == "yes":
        return ["cpc_80"], "CPC s.80"
    return [], ""


def _computed_limit(template: DraftTemplate, fields: dict[str, str]) -> dict[str, Any] | None:
    """The one date a form can compute: the sixty days for a discharge application."""
    if template.key != "discharge_application" or not fields.get("trigger_date"):
        return None
    try:
        start = date.fromisoformat(fields["trigger_date"])
    except ValueError:
        return None
    label = "BNSS s.250(1)" if fields.get("discharge_forum") == "sessions" else "BNSS s.262(1)"
    return {
        "label": "Last day for a discharge application",
        "date": (start + timedelta(days=60)).isoformat(),
        "provision": label,
        "computed_from": f"sixty days from {start.isoformat()}",
    }


def _numbered(items: list[str], start: int = 1) -> list[str]:
    return [f"{index}. {item}" for index, item in enumerate(items, start)]


def _citation_marker(grounds: list[dict[str, Any]], authorities: list[dict[str, Any]]) -> dict[str, int]:
    numbers: dict[str, int] = {}
    for item in authorities:
        numbers.setdefault(item["chunk_id"], len(numbers) + 1)
    for ground in grounds:
        for citation in ground["citations"]:
            if citation.get("scope") != "private_case":
                numbers.setdefault(citation["chunk_id"], len(numbers) + 1)
    return numbers


def _authority_line(source: dict[str, Any], number: int) -> str:
    note = authority_currency_note(
        DraftAuthority(
            chunk_id=source["chunk_id"],
            title=source["title"],
            section=source.get("section"),
            page_start=source["page_start"],
            page_end=source["page_end"],
            excerpt=source["excerpt"],
            reranker_score=float(source.get("relevance_score") or 0),
            current_status=source.get("current_status"),
            repeal_label=source.get("repeal_label"),
            replaced_by=source.get("replaced_by"),
            repealed_on=source.get("repealed_on"),
        )
    )
    section = f", {source['section']}" if source.get("section") else ""
    return f"[{number}] {source['title']}{section}, pp. {source['page_start']}-{source['page_end']}{note}"


def _facts_block(facts: str) -> list[str]:
    return ["FACTS AS INSTRUCTED", facts.strip() or REQUIRED, ""]


def _grounds_block(heading: str, grounds: list[dict[str, Any]], numbers: dict[str, int]) -> list[str]:
    lines = [heading]
    if not grounds:
        lines.append(f"{REQUIRED} No ground passed the check against its sources. Add your own.")
    for index, ground in enumerate(grounds, 1):
        markers = "".join(
            f"[{numbers[item['chunk_id']]}]" for item in ground["citations"] if item["chunk_id"] in numbers
        )
        lines.append(f"{index}. {ground['text']} {markers}".rstrip())
    lines.append("")
    return lines


def _statutory_block(keys: list[str]) -> list[str]:
    if not keys:
        return []
    lines = ["PROVISION RELIED ON, AS IT READS"]
    lines.extend(f'{PROVISIONS[key].label}: "{PROVISIONS[key].quote}"' for key in keys)
    lines.append("")
    return lines


def _authorities_block(authorities: list[dict[str, Any]], numbers: dict[str, int]) -> list[str]:
    lines = ["AUTHORITIES TO REVIEW"]
    if not authorities:
        lines.append("No authority was retrieved. Nothing has been inserted from memory.")
    lines.extend(_authority_line(item, numbers[item["chunk_id"]]) for item in authorities)
    lines.append("")
    return lines


def _caption(fields: dict[str, str], title_line: str) -> list[str]:
    reference = (fields.get("case_reference") or "").strip()
    return [
        f"IN THE COURT OF {_value(fields, 'court')}",
        *([reference] if reference else []),
        "",
        f"{_value(fields, 'applicant')} ... Applicant",
        "versus",
        f"{_value(fields, 'respondent')} ... Respondent",
        "",
        title_line,
        "",
    ]


def _signature(fields: dict[str, str]) -> list[str]:
    place = (fields.get("place") or "").strip() or REQUIRED
    advocate = (fields.get("advocate") or "").strip() or REQUIRED
    return [f"Place: {place}", "Date: [INFORMATION REQUIRED]", "", f"Advocate for the party: {advocate}"]


def render_draft(
    template: DraftTemplate,
    fields: dict[str, str],
    facts: str,
    grounds: list[dict[str, Any]],
    authorities: list[dict[str, Any]],
) -> str:
    keys, anchor = _statutory_keys(template, fields)
    numbers = _citation_marker(grounds, authorities)
    lines: list[str] = [DRAFT_DISCLAIMER, ""]
    if template.key == "bail_application":
        route = BAIL_ROUTES.get(fields.get("bail_route") or "")
        relief = route[0] if route else REQUIRED
        lines += _caption(fields, f"APPLICATION FOR {relief.upper()} UNDER {anchor}")
        lines += [f"Offence(s) alleged: {_value(fields, 'offence')}"]
        if (fields.get("custody") or "").strip():
            lines += [f"Custody: {fields['custody'].strip()}"]
        lines += [f"Previous applications: {(fields.get('previous_applications') or '').strip() or 'State whether any was made, and its result.'}", ""]
        lines += _facts_block(facts) + _statutory_block(keys) + _grounds_block("GROUNDS", grounds, numbers)
        lines += ["PRAYER", f"It is prayed that this Hon'ble Court may be pleased to grant {relief} to the applicant, on such terms as it thinks fit.", ""]
    elif template.key == "discharge_application":
        lines += _caption(fields, f"APPLICATION FOR DISCHARGE UNDER {anchor}")
        lines += [f"Offence(s) charged: {_value(fields, 'offence')}", ""]
        limit = _computed_limit(template, fields)
        if limit:
            lines += [f"Computed last day: {limit['date']} ({limit['computed_from']}, {limit['provision']}). Confirm before filing.", ""]
        lines += _facts_block(facts) + _statutory_block(keys) + _grounds_block("GROUNDS", grounds, numbers)
        lines += ["PRAYER", "It is prayed that this Hon'ble Court may be pleased to discharge the accused.", ""]
    elif template.key == "quashing_petition":
        lines += _caption(fields, f"PETITION UNDER {anchor}")
        lines += [f"Proceeding sought to be quashed: {_value(fields, 'impugned')}", f"Offence(s) alleged: {_value(fields, 'offence')}", ""]
        lines += _facts_block(facts) + _statutory_block(keys) + _grounds_block("GROUNDS", grounds, numbers)
        lines += ["PRAYER", f"It is prayed that this Hon'ble Court may be pleased to quash {_value(fields, 'impugned')}.", ""]
    elif template.key == "reply":
        lines += _caption(fields, f"REPLY TO {_value(fields, 'responding_to').upper()}")
        if (fields.get("relief_opposed") or "").strip():
            lines += [f"Opposed: {fields['relief_opposed'].strip()}", ""]
        lines += ["PARA-WISE REPLY", f"{REQUIRED} Answer each paragraph of the filing: admitted, denied, or not within knowledge.", ""]
        lines += _facts_block(facts) + _grounds_block("SUBMISSIONS", grounds, numbers)
        lines += ["PRAYER", "It is prayed that this Hon'ble Court may be pleased to dismiss the application.", ""]
    elif template.key == "legal_notice":
        lines += [
            "LEGAL NOTICE", "",
            f"To: {_value(fields, 'recipient')}", _value(fields, "recipient_address"), "",
            f"Under instructions from and on behalf of {_value(fields, 'sender')}, you are given notice as follows.", "",
        ]
        lines += _facts_block(facts) + _statutory_block(keys) + _grounds_block("GROUNDS", grounds, numbers)
        lines += [
            "DEMAND", _value(fields, "demand"), "",
            f"You are called upon to comply within {_value(fields, 'compliance_period')} of receiving this notice, "
            "failing which my client reserves the right to take such proceedings as may be advised, at your risk as to costs.",
            "",
        ]
    elif template.key == "written_submissions":
        lines += _caption(fields, "WRITTEN SUBMISSIONS")
        if (fields.get("stage") or "").strip():
            lines += [f"Stage: {fields['stage'].strip()}", ""]
        if (fields.get("points_for_determination") or "").strip():
            lines += ["POINTS FOR DETERMINATION", fields["points_for_determination"].strip(), ""]
        lines += _facts_block(facts) + _grounds_block("SUBMISSIONS", grounds, numbers)
    else:  # vakalatnama
        lines += [
            f"IN THE COURT OF {_value(fields, 'court')}", _value(fields, "case_reference"), "", "VAKALATNAMA", "",
            f"I, {_value(fields, 'client')}, {_value(fields, 'client_role')} in the above matter, appoint "
            f"{_value(fields, 'advocate')}, Advocate (Enrolment No. {_value(fields, 'enrolment')}), to appear, act and plead "
            "for me in this matter, and to sign and file what is necessary in it.", "",
            f"Address for service: {_value(fields, 'address')}", "",
        ]
        lines += _statutory_block(keys)
        lines += [
            f"Place: {(fields.get('place') or '').strip() or REQUIRED}", "Date: [INFORMATION REQUIRED]", "",
            "Signature of client: ____________", "", "Accepted. Signature of advocate: ____________",
        ]
        return "\n".join(lines).strip()
    if template.retrieval_hint or template.uses_grounds:
        lines += _authorities_block(authorities, numbers)
    lines += _signature(fields)
    return "\n".join(lines).strip()


def _check_rows(text: str) -> list[dict[str, Any]]:
    return [
        {
            "citation": check.citation, "code": check.code, "section": check.section,
            "finding": check.finding.value, "successors": list(check.successors),
            "advice": check.advice, "needs_attention": check.needs_attention,
        }
        for check in check_authorities(text)
    ]


def missing_fields(template: DraftTemplate, fields: dict[str, str]) -> list[str]:
    return [item.label for item in template.fields if item.required and not (fields.get(item.name) or "").strip()]


async def create_draft(
    *,
    retrieval: HybridRetrievalService,
    llm: OllamaClient,
    case_id: str,
    draft_type: str,
    fields: dict[str, str],
    facts: str,
    instructions: str | None,
) -> dict[str, Any]:
    template = TEMPLATES[draft_type]
    evidence = Evidence()
    notes: list[str] = []
    grounds: list[dict[str, Any]] = []
    rejected = 0
    if template.uses_grounds:
        query = " ".join(
            part for part in (facts, fields.get("offence"), template.retrieval_hint, instructions) if part
        )
        try:
            evidence = await gather_evidence(retrieval, query or template.title, case_id=case_id)
        except Exception:
            # Reported in the draft. An empty authorities list with no reason
            # reads as "nothing relevant exists".
            notes.append("The corpus could not be searched, so no authority was inserted.")
        if evidence.withheld_superseded:
            notes.append(f"{evidence.withheld_superseded} superseded passage(s) were held back from this draft.")
        authorities = [item for item in evidence.sources() if item["scope"] == "global"]
        grounds, rejected, note = await propose_verified_grounds(
            llm, draft_title=template.title, facts=facts, instructions=instructions, evidence=evidence
        )
        notes.append(note)
    else:
        authorities = []
    # Every inserted authority goes through the check on its own, including what
    # its passage cites: a 2019 judgment construing IPC s.302 is a current
    # authority on a renumbered provision, and the drafter needs to see that.
    for item in authorities:
        item["authority_check"] = _check_rows(f"{item.get('section') or ''} {item['excerpt']}")
    rendered = render_draft(template, fields, facts, grounds, authorities)
    missing = missing_fields(template, fields)
    keys, _ = _statutory_keys(template, fields)
    return {
        "draft_type": draft_type,
        "title": template.title,
        "fields": fields,
        "facts": facts,
        "grounds": grounds,
        "rejected_ground_count": rejected,
        "authorities": authorities,
        "statutory_provisions": provision_sources(*keys),
        "authority_checks": _check_rows(rendered),
        "computed_limit": _computed_limit(template, fields),
        "missing_fields": missing,
        "notes": notes,
        "rendered_text": rendered,
        "disclaimer": DRAFT_DISCLAIMER,
    }
