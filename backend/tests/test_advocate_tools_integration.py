"""The advocate tools through the API, with a real database and fake model.

Covers what only exists across the boundary: ownership on every route, what gets
saved, what comes back on reading, and a debate surviving as a durable job.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import delete, select

from app.agents.advocate_agents import BriefDraft, Evidence, SynopsisClaim, SynopsisDraft, build_verified_brief
from app.core.database import AsyncSessionLocal
from app.models import AdvocateWorkProduct, AuditLog, Case, CaseDocument, Job, JobEvent, MatterCalendarEvent, User
from app.models.enums import JobStatus
from app.routers.advocate_tools import AdvocateRuntime, get_advocate_runtime, router as advocate_router
from app.routers.strategy import StrategyRuntime, get_strategy_runtime
from app.services.job_worker import DurableJobWorker
from app.services.judgment_index import JudgmentIndex
from main import app
from tests.advocate_fakes import FakeRetrieval, PromptReadingLLM, judgment_chunk
from tests.helpers import provision_test_user, unique_email

PASSWORD = "CorrectHorseBattery99!"
AJITH = "THE STATE OF KERALA vs K.AJITH Crl.A. No. 697/2021"
ARNESH = "ARNESH KUMAR vs STATE OF BIHAR Crl.A. No. 1277/2014"
FACTS = "The client was arrested after a search of the premises and has been in custody since."


def corpus() -> list:
    return [
        judgment_chunk(
            "kerala", AJITH, 1,
            "The appellant was arrested after a search of the premises by the police. Bail was refused by the Sessions Court.",
            year=2021,
        ),
        judgment_chunk(
            "arnesh", ARNESH, 1,
            "The accused was arrested for dowry demand without any search of premises. Arrest should not be mechanical.",
            year=2014,
        ),
        judgment_chunk(
            "ipc-note", "The Indian Penal Code, 1860", 1,
            "Whoever commits murder shall be punished under section 302 of the Indian Penal Code.",
            year=None,
        ),
    ]


class Harness:
    def __init__(self) -> None:
        self.user_ids: list[uuid.UUID] = []
        self.case_ids: list[uuid.UUID] = []
        self.retrieval = FakeRetrieval(corpus())
        self.llm = PromptReadingLLM()
        self.index = JudgmentIndex(self.retrieval.client, "corpus", ttl_seconds=0)
        self.client: AsyncClient
        self.owner: dict[str, str]
        self.rival: dict[str, str]
        self.police: dict[str, str]
        self.case_id: uuid.UUID
        self.rival_case_id: uuid.UUID

    async def user(self, role: str) -> dict[str, str]:
        made = await provision_test_user(
            name=f"{role} user", email=unique_email(f"advocate-{role}"), password=PASSWORD, role=role
        )
        self.user_ids.append(uuid.UUID(made["user"]["id"]))
        return {"Authorization": f"Bearer {made['access_token']}"}

    async def case(self, headers: dict[str, str]) -> uuid.UUID:
        response = await self.client.post("/cases", json={"title": "A case for the tools"}, headers=headers)
        assert response.status_code == 201, response.text
        case_id = uuid.UUID(response.json()["id"])
        self.case_ids.append(case_id)
        return case_id

    async def add_case_file(self, case_id: uuid.UUID, text: str) -> uuid.UUID:
        async with AsyncSessionLocal() as session:
            document = CaseDocument(case_id=case_id, file_url=f"s3://b/{uuid.uuid4()}", doc_type="order", ocr_text=text)
            session.add(document)
            await session.commit()
            await session.refresh(document)
        for index, sentence in enumerate(text.split("\n"), 1):
            record = SimpleNamespace(
                id=f"{document.id}-{index}",
                payload={
                    "chunk_id": f"{document.id}-{index}",
                    "document_id": str(document.id),
                    "case_id": str(case_id),
                    "corpus_scope": "private_case",
                    "title": "order.pdf",
                    "doc_type": "order",
                    "page_start": index,
                    "page_end": index,
                    "text": sentence,
                },
            )
            self.retrieval.case_files.append(record)
            self.retrieval.client.records.append(record)
        return document.id


@pytest_asyncio.fixture(loop_scope="session")
async def harness():
    state = Harness()
    app.dependency_overrides[get_advocate_runtime] = lambda: AdvocateRuntime(state.retrieval, state.llm, state.index)
    app.dependency_overrides[get_strategy_runtime] = lambda: StrategyRuntime(state.retrieval, state.llm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        state.client = client
        state.owner = await state.user("advocate")
        state.rival = await state.user("advocate")
        state.police = await state.user("police")
        state.case_id = await state.case(state.owner)
        state.rival_case_id = await state.case(state.rival)
        try:
            yield state
        finally:
            app.dependency_overrides.pop(get_advocate_runtime, None)
            app.dependency_overrides.pop(get_strategy_runtime, None)
            async with AsyncSessionLocal() as session:
                await session.execute(delete(Job).where(Job.user_id.in_(state.user_ids)))
                await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(state.user_ids)))
                await session.execute(delete(Case).where(Case.id.in_(state.case_ids)))
                await session.execute(delete(User).where(User.id.in_(state.user_ids)))
                await session.commit()


# ------------------------------------------------------------------ ownership


def _case_routes() -> list[tuple[str, str]]:
    from main import app as live

    found: list[tuple[str, str]] = []

    def walk(container) -> None:
        for route in getattr(container, "routes", []):
            if isinstance(route, APIRoute):
                if "{case_id}" in route.path and (
                    "/advocate/" in route.path or "/strategy/defence-analys" in route.path
                ):
                    found.extend((method, route.path) for method in route.methods)
            else:
                nested = getattr(route, "original_router", None) or route
                if nested is not route or hasattr(nested, "routes"):
                    walk(nested)

    walk(live)
    return sorted(set(found))


BODIES = {
    "/advocate/bail/assess": {"classification": "bailable"},
    "/advocate/drafts": {"draft_type": "vakalatnama", "fields": {}, "facts": ""},
    "/advocate/briefs": {"kind": "brief"},
    "/advocate/opponent-check": {"text": "Section 302 IPC"},
    "/advocate/compare": {"first_judgment_id": "kerala", "second_judgment_id": "arnesh"},
    "/advocate/debates": {"proposition": "Bail ought to follow on these facts."},
    "/advocate/calendar": {"title": "Hearing", "due_on": "2027-01-01"},
    "/advocate/calendar/limitation": {"article": "art_137", "runs_from": "2026-01-01"},
    "/advocate/calendar/{event_id}": {"completed": True},
}


@pytest.mark.parametrize(("method", "path"), _case_routes())
async def test_a_foreign_case_is_refused_on_every_route(harness: Harness, method: str, path: str) -> None:
    """Walks the routing table, so a route added later is covered without being named."""
    url = path.format(
        case_id=harness.case_id, event_id=uuid.uuid4(), job_id=uuid.uuid4(), work_id=uuid.uuid4(), analysis_id=uuid.uuid4()
    )
    suffix = path.split("{case_id}")[1]
    headers = {**harness.rival, "Idempotency-Key": f"cross-tenant-{uuid.uuid4().hex}"}
    if method == "GET":
        response = await harness.client.get(url, headers=headers)
    elif method == "DELETE":
        response = await harness.client.delete(url, headers=headers)
    else:
        body = BODIES.get(suffix, {"case_scenario": FACTS})
        response = await harness.client.request(method, url, json=body, headers=headers)
    assert response.status_code == 404, f"{method} {path}: {response.status_code} {response.text}"
    assert harness.llm.prompts == []
    assert harness.retrieval.calls == []


def test_the_walk_found_the_routes() -> None:
    """A vacuity guard for the parametrisation above."""
    assert len(_case_routes()) >= 16


async def test_a_police_officer_cannot_use_the_advocate_tools(harness: Harness) -> None:
    for path in ("/advocate/judgments", "/advocate/calendar", "/advocate/draft-templates", "/advocate/limitation-articles"):
        assert (await harness.client.get(path, headers=harness.police)).status_code == 403
    response = await harness.client.post("/advocate/treatment", json={"reference": "Arnesh Kumar"}, headers=harness.police)
    assert response.status_code == 403


async def test_nobody_anonymous_gets_in(harness: Harness) -> None:
    assert (await harness.client.get("/advocate/judgments")).status_code == 401
    assert (await harness.client.get(f"/cases/{harness.case_id}/advocate/work")).status_code == 401


async def test_a_work_id_from_another_case_is_not_found(harness: Harness) -> None:
    other = await harness.case(harness.owner)
    made = await harness.client.post(
        f"/cases/{other}/advocate/drafts",
        json={"draft_type": "vakalatnama", "fields": {}, "facts": ""},
        headers=harness.owner,
    )
    assert made.status_code == 201, made.text
    work_id = made.json()["id"]
    assert (await harness.client.get(f"/cases/{other}/advocate/work/{work_id}", headers=harness.owner)).status_code == 200
    assert (await harness.client.get(f"/cases/{harness.case_id}/advocate/work/{work_id}", headers=harness.owner)).status_code == 404


async def test_an_event_id_from_another_case_is_not_found(harness: Harness) -> None:
    other = await harness.case(harness.owner)
    made = await harness.client.post(
        f"/cases/{other}/advocate/calendar", json={"title": "Hearing", "due_on": "2027-01-01"}, headers=harness.owner
    )
    event_id = made.json()["id"]
    response = await harness.client.patch(
        f"/cases/{harness.case_id}/advocate/calendar/{event_id}", json={"completed": True}, headers=harness.owner
    )
    assert response.status_code == 404


# ----------------------------------------------------------------------- bail


async def test_bail_assessment_computes_and_cites_and_can_be_saved(harness: Harness) -> None:
    response = await harness.client.post(
        f"/cases/{harness.case_id}/advocate/bail/assess",
        json={
            "routes": ["default"], "as_of": "2026-11-04", "gravity": "other",
            "first_remand_on": "2026-01-01", "report_filed": False, "offence_description": "search of the premises",
            "save": True,
        },
        headers=harness.owner,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    route = body["routes"][0]
    assert route["status"] == "entitled_on_text"
    assert route["dates"][0]["date"] == "2026-03-02"
    assert route["sources"][0]["section"].startswith("BNSS s.187")
    assert route["sources"][0]["current_status"] == "current"
    assert body["coverage"]["judgments_held"] == 3
    assert body["authorities"], "retrieved passages come back with the assessment"
    assert harness.llm.prompts == [], "no model reads the facts or writes the finding"
    saved = await harness.client.get(f"/cases/{harness.case_id}/advocate/work/{body['work_product_id']}", headers=harness.owner)
    assert saved.json()["content"]["routes"][0]["status"] == "entitled_on_text"


async def test_bail_still_answers_when_the_corpus_is_down(harness: Harness) -> None:
    harness.retrieval.fail = True
    harness.retrieval.client.fail = True
    response = await harness.client.post(
        f"/cases/{harness.case_id}/advocate/bail/assess", json={"classification": "bailable"}, headers=harness.owner
    )
    assert response.status_code == 200
    body = response.json()
    assert body["authorities"] == []
    assert "could not be searched" in body["authorities_note"]
    assert body["coverage"]["judgments_held"] is None


# ------------------------------------------------------------------ drafting


async def test_a_draft_publishes_only_verified_grounds_and_checks_its_authorities(harness: Harness) -> None:
    response = await harness.client.post(
        f"/cases/{harness.case_id}/advocate/drafts",
        json={
            "draft_type": "bail_application",
            "fields": {"bail_route": "anticipatory", "court": "Sessions Court, Guntur", "applicant": "A", "respondent": "State", "offence": "s.302 IPC"},
            "facts": FACTS,
        },
        headers=harness.owner,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    content = body["content"]
    assert body["kind"] == "draft:bail_application" and body["version"] == 1
    grounds = [item["text"] for item in content["grounds"]]
    assert grounds, "the supported proposals survive"
    assert content["rejected_ground_count"] == 3
    for trap in ("section 999", "will win", "nobody retrieved"):
        assert not any(trap in text for text in grounds)
        assert trap not in content["rendered_text"]
    assert all(citation["verification_status"] == "verified" for ground in content["grounds"] for citation in ground["citations"])
    assert content["statutory_provisions"][0]["section"] == "BNSS s.482(1)"
    assert "BNSS s.482" in content["rendered_text"]
    assert content["rendered_text"].startswith("DRAFT FOR REVIEW")
    # The typed-in IPC section is flagged, as is the one in a retrieved passage.
    assert any(row["citation"] == "IPC s.302" and row["needs_attention"] for row in content["authority_checks"])
    ipc = next(item for item in content["authorities"] if item["chunk_id"] == "ipc-note-chunk-1")
    assert any(row["citation"] == "IPC s.302" for row in ipc["authority_check"])
    assert all(item["scope"] == "global" for item in content["authorities"])


async def test_missing_form_fields_stay_visibly_missing(harness: Harness) -> None:
    response = await harness.client.post(
        f"/cases/{harness.case_id}/advocate/drafts",
        json={"draft_type": "vakalatnama", "fields": {"court": "High Court"}, "facts": ""},
        headers=harness.owner,
    )
    body = response.json()
    assert body["status"] == "incomplete"
    assert "Client" in body["content"]["missing_fields"]
    assert "[INFORMATION REQUIRED]" in body["content"]["rendered_text"]
    assert harness.llm.prompts == [], "a vakalatnama involves no model"


async def test_every_template_renders(harness: Harness) -> None:
    catalogue = (await harness.client.get("/advocate/draft-templates", headers=harness.owner)).json()["templates"]
    assert {item["key"] for item in catalogue} == {
        "bail_application", "discharge_application", "quashing_petition", "reply",
        "legal_notice", "vakalatnama", "written_submissions",
    }
    for template in catalogue:
        fields = {
            field["name"]: (field["options"][0]["value"] if field["options"] else "2026-01-01" if field["kind"] == "date" else "Filled in")
            for field in template["fields"]
        }
        response = await harness.client.post(
            f"/cases/{harness.case_id}/advocate/drafts",
            json={"draft_type": template["key"], "fields": fields, "facts": FACTS},
            headers=harness.owner,
        )
        assert response.status_code == 201, response.text
        content = response.json()["content"]
        assert content["missing_fields"] == []
        assert content["rendered_text"].startswith("DRAFT FOR REVIEW"), template["key"]


async def test_discharge_computes_its_sixty_days(harness: Harness) -> None:
    response = await harness.client.post(
        f"/cases/{harness.case_id}/advocate/drafts",
        json={
            "draft_type": "discharge_application",
            "fields": {"discharge_forum": "warrant", "trigger_date": "2026-01-01"},
            "facts": FACTS,
        },
        headers=harness.owner,
    )
    content = response.json()["content"]
    assert content["computed_limit"]["date"] == "2026-03-02"
    assert content["computed_limit"]["provision"] == "BNSS s.262(1)"


async def test_a_draft_survives_the_model_being_down_and_says_so(harness: Harness) -> None:
    harness.llm.drafter_available = False
    response = await harness.client.post(
        f"/cases/{harness.case_id}/advocate/drafts",
        json={"draft_type": "reply", "fields": {"responding_to": "bail petition"}, "facts": FACTS},
        headers=harness.owner,
    )
    assert response.status_code == 201
    content = response.json()["content"]
    assert content["grounds"] == []
    assert any("language model was unavailable" in note for note in content["notes"])
    assert content["authorities"], "what retrieval found is still offered"


async def test_a_second_draft_is_a_new_version_and_the_first_is_untouched(harness: Harness) -> None:
    url = f"/cases/{harness.case_id}/advocate/drafts"
    first = (await harness.client.post(url, json={"draft_type": "vakalatnama", "fields": {"court": "One"}, "facts": ""}, headers=harness.owner)).json()
    second = (await harness.client.post(url, json={"draft_type": "vakalatnama", "fields": {"court": "Two"}, "facts": ""}, headers=harness.owner)).json()
    assert second["version"] == first["version"] + 1
    reread = (await harness.client.get(f"/cases/{harness.case_id}/advocate/work/{first['id']}", headers=harness.owner)).json()
    assert reread["content"]["rendered_text"] == first["content"]["rendered_text"]


# ------------------------------------------------------------------ calendar


async def test_calendar_crud_and_states(harness: Harness) -> None:
    url = f"/cases/{harness.case_id}/advocate/calendar"
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    made = await harness.client.post(url, json={"kind": "hearing", "title": "Arguments", "due_on": yesterday}, headers=harness.owner)
    assert made.status_code == 201, made.text
    event = made.json()
    assert event["state"] == "overdue"
    done = await harness.client.patch(f"{url}/{event['id']}", json={"completed": True}, headers=harness.owner)
    assert done.json()["state"] == "done"
    moved = await harness.client.patch(
        f"{url}/{event['id']}",
        json={"completed": False, "due_on": (date.today() + timedelta(days=30)).isoformat(), "notes": "Bring file"},
        headers=harness.owner,
    )
    assert moved.json()["state"] == "upcoming" and moved.json()["notes"] == "Bring file"
    assert (await harness.client.delete(f"{url}/{event['id']}", headers=harness.owner)).status_code == 204
    assert (await harness.client.get(url, headers=harness.owner)).json()["events"] == []


async def test_the_cross_case_calendar_is_only_my_own_cases(harness: Harness) -> None:
    for headers, case_id, title in (
        (harness.owner, harness.case_id, "Mine"),
        (harness.rival, harness.rival_case_id, "Theirs"),
    ):
        await harness.client.post(
            f"/cases/{case_id}/advocate/calendar", json={"title": title, "due_on": "2027-01-01"}, headers=headers
        )
    events = (await harness.client.get("/advocate/calendar", headers=harness.owner)).json()["events"]
    assert [item["title"] for item in events] == ["Mine"]
    assert events[0]["case_title"] == "A case for the tools"


async def test_limitation_calculation_and_adding_it_to_the_calendar(harness: Harness) -> None:
    url = f"/cases/{harness.case_id}/advocate/calendar/limitation"
    response = await harness.client.post(
        url, json={"article": "art_116_b", "runs_from": "2026-03-01", "add_to_calendar": True}, headers=harness.owner
    )
    body = response.json()
    assert body["last_day"] == "2026-03-31"
    assert body["event"]["kind"] == "limitation"
    assert body["event"]["basis"]["provision"] == "Limitation Act, Schedule, Art. 116(b)"
    refused = await harness.client.post(url, json={"article": "art_999", "runs_from": "2026-03-01"}, headers=harness.owner)
    assert refused.status_code == 422
    assert "No date" in refused.json()["detail"]


# --------------------------------------------------------------------- brief


async def test_a_brief_keeps_only_what_its_case_documents_state(harness: Harness) -> None:
    await harness.add_case_file(
        harness.case_id,
        "The accused was remanded to custody by the Magistrate.\nThe charge sheet cites section 438 of the CrPC.",
    )
    await harness.add_case_file(harness.rival_case_id, "Rival secret strategy memorandum about their client.")
    response = await harness.client.post(f"/cases/{harness.case_id}/advocate/briefs", json={"kind": "brief"}, headers=harness.owner)
    assert response.status_code == 201, response.text
    content = response.json()["content"]
    claims = [claim["text"] for section in content["sections"] for claim in section["claims"]]
    assert "The accused was remanded to custody by the Magistrate." in claims
    assert not any("will win" in text for text in claims)
    assert "Rival secret" not in str(content)
    assert "Rival secret" not in " ".join(harness.llm.prompts)
    assert content["rejected_count"] == 1
    assert any(row["citation"] == "CrPC s.438" and row["needs_attention"] for row in content["provisions_in_record"])


async def test_a_synopsis_stays_within_its_sections(harness: Harness) -> None:
    await harness.add_case_file(harness.case_id, "On 3 March the FIR was registered.\nThe issue is whether the search was lawful.")
    response = await harness.client.post(f"/cases/{harness.case_id}/advocate/briefs", json={"kind": "synopsis"}, headers=harness.owner)
    content = response.json()["content"]
    assert content["sections"], "a synopsis of a real file must show something"
    assert {section["key"] for section in content["sections"]} <= {"chronology", "issues", "relief"}
    assert response.json()["kind"] == "synopsis"


async def test_a_synopsis_asks_the_model_only_for_sections_it_can_show() -> None:
    """On one case the model filed all 20 statements under "facts", and the advocate saw nothing."""
    asked_for: list[type] = []

    async def structured(_prompt: str, schema: type):
        asked_for.append(schema)
        return schema()

    llm = SimpleNamespace(structured=structured)
    await build_verified_brief(llm, kind="synopsis", focus=None, evidence=Evidence())
    await build_verified_brief(llm, kind="brief", focus=None, evidence=Evidence())
    assert asked_for[0] is SynopsisDraft and asked_for[1] is BriefDraft
    with pytest.raises(ValidationError):
        SynopsisClaim(text="The FIR was registered.", source_ids=[], section="facts")


async def test_a_statement_proposed_twice_is_kept_once_and_first() -> None:
    claim = {"source_ids": [], "section": "chronology"}
    draft = SynopsisDraft.model_validate(
        {"claims": [{"text": "First fact.", **claim}, {"text": "Second fact.", **claim}, {"text": " first  FACT. ", **claim}]}
    )
    asked: list[list[str]] = []

    async def structured(prompt: str, schema: type):
        if schema is SynopsisDraft:
            return draft
        asked.append(prompt)
        return schema()

    result = await build_verified_brief(
        SimpleNamespace(structured=structured), kind="synopsis", focus=None, evidence=Evidence()
    )
    assert result["proposed_count"] == 2


async def test_a_brief_with_no_documents_says_so(harness: Harness) -> None:
    response = await harness.client.post(f"/cases/{harness.case_id}/advocate/briefs", json={}, headers=harness.owner)
    assert response.status_code == 409
    assert "nothing to summarise" in response.json()["detail"]


async def test_a_brief_cannot_name_another_cases_document(harness: Harness) -> None:
    foreign = await harness.add_case_file(harness.rival_case_id, "Rival material.")
    response = await harness.client.post(
        f"/cases/{harness.case_id}/advocate/briefs", json={"document_ids": [str(foreign)]}, headers=harness.owner
    )
    assert response.status_code == 404


async def test_a_brief_reports_the_model_being_down_rather_than_an_empty_brief(harness: Harness) -> None:
    await harness.add_case_file(harness.case_id, "Something on record.")
    harness.llm.drafter_available = False
    response = await harness.client.post(f"/cases/{harness.case_id}/advocate/briefs", json={}, headers=harness.owner)
    assert response.status_code == 503


# ------------------------------------------------------------- held material


async def test_judgment_list_states_coverage(harness: Harness) -> None:
    body = (await harness.client.get("/advocate/judgments", headers=harness.owner)).json()
    assert body["coverage"]["judgments_held"] == 3
    assert {item["document_id"] for item in body["judgments"]} == {"kerala", "arnesh", "ipc-note"}


async def test_precedents_and_treatment_state_their_scope(harness: Harness) -> None:
    precedents = await harness.client.post(
        "/advocate/precedents", json={"query": "arrested search premises", "court": "Supreme Court of India"}, headers=harness.owner
    )
    assert precedents.status_code == 200
    assert precedents.json()["coverage"]["judgments_searched"] == 3
    reversed_years = await harness.client.post(
        "/advocate/precedents", json={"query": "arrested", "year_from": 2024, "year_to": 2020}, headers=harness.owner
    )
    assert reversed_years.status_code == 422
    treatment = await harness.client.post("/advocate/treatment", json={"reference": "Arnesh Kumar v. State of Bihar"}, headers=harness.owner)
    assert treatment.status_code == 200
    assert treatment.json()["label"].startswith("Partial check")


async def test_a_down_corpus_is_reported_not_answered(harness: Harness) -> None:
    harness.retrieval.client.fail = True
    response = await harness.client.post("/advocate/treatment", json={"reference": "Arnesh Kumar"}, headers=harness.owner)
    assert response.status_code == 503
    assert (await harness.client.get("/advocate/judgments", headers=harness.owner)).status_code == 503


async def test_opponent_check_from_paste_and_from_a_case_document(harness: Harness) -> None:
    url = f"/cases/{harness.case_id}/advocate/opponent-check"
    pasted = await harness.client.post(
        url, json={"text": "Reliance on Arnesh Kumar v. State of Bihar and section 302 IPC.", "save": True}, headers=harness.owner
    )
    assert pasted.status_code == 200, pasted.text
    assert pasted.json()["cases"][0]["held"] is True
    assert pasted.json()["work_product_id"]
    document = await harness.add_case_file(harness.case_id, "The respondent cites section 438 of the CrPC.")
    filed = await harness.client.post(url, json={"document_id": str(document)}, headers=harness.owner)
    assert any(row["citation"] == "CrPC s.438" for row in filed.json()["provisions"])
    foreign = await harness.add_case_file(harness.rival_case_id, "Their filing.")
    assert (await harness.client.post(url, json={"document_id": str(foreign)}, headers=harness.owner)).status_code == 404
    assert (await harness.client.post(url, json={}, headers=harness.owner)).status_code == 422


# ---------------------------------------------------------------- comparison


async def test_comparison_checks_each_side_only_against_itself(harness: Harness) -> None:
    response = await harness.client.post(
        f"/cases/{harness.case_id}/advocate/compare",
        json={"first_judgment_id": "kerala", "second_judgment_id": "arnesh", "focus": "search"},
        headers=harness.owner,
    )
    assert response.status_code == 201, response.text
    content = response.json()["content"]
    assert content["coverage"]["judgments_searched"] == 2
    assert content["coverage"]["judgments_held"] == 3
    point = content["points"][0]
    assert point["dimension"] == "The incident"
    assert "search of the premises" in point["first"]["text"]
    assert point["second"]["citations"][0]["document_id"] == "arnesh"
    # The fake's crossed citations name the other judgment's ids: refused on both sides.
    assert [item["dimension"] for item in content["points"]] == ["The incident"]
    assert content["verified_count"] == 2 and content["proposed_count"] == 4
    assert "does not say which position is stronger" in content["limit_note"]


async def test_comparison_against_this_matters_facts(harness: Harness) -> None:
    response = await harness.client.post(
        f"/cases/{harness.case_id}/advocate/compare",
        json={"first_judgment_id": "kerala", "matter_facts": "The client was arrested after a search of the premises."},
        headers=harness.owner,
    )
    assert response.status_code == 201, response.text
    content = response.json()["content"]
    assert content["second_is_user_account"] is True
    assert "unverified" in content["second_title"]


async def test_comparison_refuses_a_judgment_not_held_or_the_same_one_twice(harness: Harness) -> None:
    url = f"/cases/{harness.case_id}/advocate/compare"
    missing = await harness.client.post(url, json={"first_judgment_id": "nope", "second_judgment_id": "kerala"}, headers=harness.owner)
    assert missing.status_code == 404
    same = await harness.client.post(url, json={"first_judgment_id": "kerala", "second_judgment_id": "kerala"}, headers=harness.owner)
    assert same.status_code == 422


# -------------------------------------------------------------------- debate


async def _start_debate(harness: Harness, *, rounds: int = 1) -> str:
    response = await harness.client.post(
        f"/cases/{harness.case_id}/advocate/debates",
        json={"proposition": "Bail ought to follow where the arrest was mechanical.", "facts": FACTS, "rounds": rounds},
        headers={**harness.owner, "Idempotency-Key": f"debate-{uuid.uuid4().hex}"},
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def _worker(harness: Harness) -> DurableJobWorker:
    return DurableJobWorker(SimpleNamespace(retrieval=harness.retrieval, llm=harness.llm))  # type: ignore[arg-type]


async def _run_one_attempt(harness: Harness, job_id: str) -> None:
    worker = _worker(harness)
    assert str(await worker._claim()) == job_id
    await worker._execute(uuid.UUID(job_id))


async def test_a_debate_runs_in_sequence_verified_and_saved(harness: Harness) -> None:
    job_id = await _start_debate(harness, rounds=2)
    await _run_one_attempt(harness, job_id)
    read = await harness.client.get(f"/cases/{harness.case_id}/advocate/debates/{job_id}", headers=harness.owner)
    body = read.json()
    assert body["status"] == "succeeded" and body["progress"] == 100
    assert body["turns_done"] == 4 == body["turns_total"]
    assert [(turn["round"], turn["side"]) for turn in body["debate"]["turns"]] == [
        (1, "for"), (1, "against"), (2, "for"), (2, "against"),
    ]
    published = str(body["debate"]["turns"])
    for trap in ("section 999", "will win", "nobody retrieved"):
        assert trap not in published
    assert body["debate"]["rejected_count"] > 0
    assert not {"winner", "verdict", "stronger_side"} & set(body["debate"])
    work = await harness.client.get(f"/cases/{harness.case_id}/advocate/work/{body['work_product_id']}", headers=harness.owner)
    assert work.json()["kind"] == "debate"
    assert "does not say which side is right" in work.json()["content"]["disclaimer"]
    # The second side was shown what the first said, so it can answer it.
    opening = body["debate"]["turns"][0]["arguments"][0]["text"]
    assert opening in harness.llm.prompts[2] or any(opening in prompt for prompt in harness.llm.prompts[1:])


async def test_progress_events_name_what_is_happening(harness: Harness) -> None:
    job_id = await _start_debate(harness)
    await _run_one_attempt(harness, job_id)
    async with AsyncSessionLocal() as session:
        events = (await session.scalars(
            select(JobEvent).where(JobEvent.job_id == uuid.UUID(job_id), JobEvent.event_type == "stage").order_by(JobEvent.id)
        )).all()
    labels = [event.data.get("label") for event in events]
    assert any("finding authority" in label for label in labels)
    assert any("checking" in label for label in labels)
    assert [event.progress for event in events] == sorted(event.progress for event in events)


async def test_a_retried_debate_resumes_and_does_not_pay_twice(harness: Harness) -> None:
    job_id = await _start_debate(harness, rounds=2)
    # First attempt dies after the first turn's draft call has been paid for.
    harness.llm.fail_after_draft_calls = 2
    await _run_one_attempt(harness, job_id)
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        assert job.status is JobStatus.QUEUED, "a model failure retries"
        done = len(job.payload["checkpoint"])
    assert done == 2
    partial = await harness.client.get(f"/cases/{harness.case_id}/advocate/debates/{job_id}", headers=harness.owner)
    assert partial.json()["debate"]["turns"][0]["side"] == "for", "finished turns are readable while it waits"

    harness.llm.fail_after_draft_calls = None
    before = harness.llm.draft_calls
    await _run_one_attempt(harness, job_id)
    assert harness.llm.draft_calls - before == 2, "only the two outstanding turns run again"
    final = await harness.client.get(f"/cases/{harness.case_id}/advocate/debates/{job_id}", headers=harness.owner)
    assert final.json()["status"] == "succeeded"
    assert len(final.json()["debate"]["turns"]) == 4


async def test_a_cancelled_debate_stops(harness: Harness) -> None:
    job_id = await _start_debate(harness, rounds=3)
    worker = _worker(harness)
    assert str(await worker._claim()) == job_id
    cancelled = await harness.client.post(f"/jobs/{job_id}/cancel", headers=harness.owner)
    assert cancelled.status_code == 200, cancelled.text
    await worker._execute(uuid.UUID(job_id))
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        assert job.status is JobStatus.CANCELLED
    rows = await harness.client.get(f"/cases/{harness.case_id}/advocate/work", headers=harness.owner)
    assert rows.json()["work"] == []


async def test_idempotency_and_listing(harness: Harness) -> None:
    url = f"/cases/{harness.case_id}/advocate/debates"
    headers = {**harness.owner, "Idempotency-Key": f"debate-{uuid.uuid4().hex}"}
    body = {"proposition": "Bail ought to follow on these facts."}
    first = await harness.client.post(url, json=body, headers=headers)
    second = await harness.client.post(url, json=body, headers=headers)
    assert first.json()["id"] == second.json()["id"]
    conflict = await harness.client.post(url, json={"proposition": "A different proposition entirely."}, headers=headers)
    assert conflict.status_code == 409
    listed = await harness.client.get(url, headers=harness.owner)
    assert [item["id"] for item in listed.json()["debates"]] == [first.json()["id"]]
    rival_view = await harness.client.get(f"/cases/{harness.rival_case_id}/advocate/debates", headers=harness.rival)
    assert rival_view.json()["debates"] == []


# -------------------------------------------------------------------- F12


async def test_a_defence_analysis_is_kept_and_reopens_as_written(harness: Harness) -> None:
    await harness.add_case_file(harness.case_id, "The forensic note reports no usable fingerprints.")
    scenario = "The client denies knowing the package was under the seat when the police searched the car."
    made = await harness.client.post(
        f"/cases/{harness.case_id}/strategy/defence-analysis", json={"case_scenario": scenario}, headers=harness.owner
    )
    assert made.status_code == 200, made.text
    body = made.json()
    assert body["id"] and body["version"] == 1
    assert body["evidence_strength"] in {"strong", "moderate", "insufficient"}
    assert body["points"], "the passages supported something"
    # What it shows: only checked points, with their sources and their strength.
    assert body["rejected_point_count"] == 1
    assert "will win" not in str(body["points"])
    assert "must not reach the reader" not in str(body)
    assert all(point["verification_reason"] == "" for point in body["points"])
    cited = {item["chunk_id"]: item for item in body["citations"]}
    for point in body["points"]:
        assert set(point["source_chunk_ids"]) <= set(cited)
    assert cited["case-scenario-input"]["verification_status"] == "unverified"
    assert any(item["verification_status"] == "verified" for item in cited.values())
    listed = await harness.client.get(f"/cases/{harness.case_id}/strategy/defence-analyses", headers=harness.owner)
    assert [row["id"] for row in listed.json()["analyses"]] == [body["id"]]
    reopened = await harness.client.get(
        f"/cases/{harness.case_id}/strategy/defence-analyses/{body['id']}", headers=harness.owner
    )
    assert reopened.json()["summary"] == body["summary"]
    assert reopened.json()["case_scenario"] == scenario
    calls = len(harness.llm.prompts)
    await harness.client.get(f"/cases/{harness.case_id}/strategy/defence-analyses/{body['id']}", headers=harness.owner)
    assert len(harness.llm.prompts) == calls, "reading does not rerun"


async def test_a_model_outage_gives_a_saved_honest_analysis_not_a_500(harness: Harness) -> None:
    harness.llm.drafter_available = False
    response = await harness.client.post(
        f"/cases/{harness.case_id}/strategy/defence-analysis",
        json={"case_scenario": "The client denies knowing about the package found under the seat of the car."},
        headers=harness.owner,
    )
    assert response.status_code == 200
    assert response.json()["evidence_strength"] == "insufficient"
    assert response.json()["points"] == []


# -------------------------------------------------------------------- saved


async def test_saved_work_lists_every_kind_newest_first_for_this_case(harness: Harness) -> None:
    case = f"/cases/{harness.case_id}/advocate"
    await harness.client.post(f"{case}/drafts", json={"draft_type": "vakalatnama", "fields": {}, "facts": ""}, headers=harness.owner)
    await harness.client.post(f"{case}/opponent-check", json={"text": "Section 302 IPC", "save": True}, headers=harness.owner)
    rows = (await harness.client.get(f"{case}/work", headers=harness.owner)).json()["work"]
    assert {row["kind"] for row in rows} == {"draft:vakalatnama", "opponent_check"}
    async with AsyncSessionLocal() as session:
        count = len((await session.scalars(select(AdvocateWorkProduct).where(AdvocateWorkProduct.case_id == harness.case_id))).all())
        events = (await session.scalars(select(MatterCalendarEvent).where(MatterCalendarEvent.case_id == harness.case_id))).all()
    assert count == 2 and list(events) == []


def test_every_route_on_the_router_is_either_case_bound_or_corpus_only() -> None:
    """A new route must not carry a case in its body without an ownership check."""
    for route in advocate_router.routes:
        assert route.path.startswith(("/advocate/", "/cases/{case_id}/advocate/")), route.path

