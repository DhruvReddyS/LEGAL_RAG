"""What an administrator may do to someone else's material, and what it leaves.

Reads are allowed on a named matter and always write a row. Writes are refused.
None of those rows may hold what the material says.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import (
    AuditLog,
    Case,
    ChatMessage,
    ChatSession,
    GeneratedDocument,
    Job,
    User,
)
from app.models.enums import CaseRoleType, ChatMessageRole, JobStatus, JobType
from app.routers.chat import get_workflow
from app.routers.retrieval import get_retrieval_service
from app.services.audit_redaction import redact_audit_metadata, trace_for_audit
from app.services.rate_limit import user_rate_limiter
from app.services.storage import attachment_disposition, content_matches_declared_type
from main import app
from tests.helpers import provision_test_user, unique_email

PASSWORD = "CorrectHorseBattery99!"
SECRET_TEXT = "my husband hit me on the fifth of march"


def _bearer(account: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {account['access_token']}"}


@pytest_asyncio.fixture(loop_scope="session")
async def world():
    """An officer with a case, a session and a job, an admin, and a stranger."""
    officer = await provision_test_user(
        name="Officer", email=unique_email("officer"), password=PASSWORD, role="police"
    )
    admin = await provision_test_user(
        name="Admin", email=unique_email("admin"), password=PASSWORD, role="admin"
    )
    stranger = await provision_test_user(
        name="Stranger", email=unique_email("stranger"), password=PASSWORD, role="police"
    )
    owner_id = uuid.UUID(officer["user"]["id"])
    async with AsyncSessionLocal() as session:
        case = Case(owner_id=owner_id, title="A matter", role_type=CaseRoleType.POLICE, status="open")
        session.add(case)
        await session.flush()
        chat = ChatSession(user_id=owner_id, title=SECRET_TEXT[:40])
        session.add(chat)
        await session.flush()
        session.add(
            ChatMessage(
                session_id=chat.id,
                role=ChatMessageRole.USER,
                content=SECRET_TEXT,
                citations=[],
            )
        )
        job = Job(
            user_id=owner_id,
            type=JobType.DEEP_REVIEW,
            status=JobStatus.SUCCEEDED,
            progress=100,
            idempotency_key=uuid.uuid4().hex,
            payload={},
            result={"answer": "the answer to the officer"},
        )
        session.add(job)
        analysis = GeneratedDocument(
            case_id=case.id,
            doc_type=f"document_analysis:{uuid.uuid4()}",
            version=1,
            content={"summary": "an analysis"},
            status="completed",
        )
        draft = GeneratedDocument(
            case_id=case.id,
            doc_type="fir",
            version=1,
            content={"facts": {"narrative": "x"}, "rendered_text": "draft"},
            status="draft",
        )
        session.add_all([analysis, draft])
        await session.commit()
        ids = SimpleNamespace(
            case=case.id,
            chat=chat.id,
            job=job.id,
            analysis=analysis.id,
            draft=draft.id,
            owner=owner_id,
            admin=uuid.UUID(admin["user"]["id"]),
            stranger=uuid.UUID(stranger["user"]["id"]),
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(
            client=client, ids=ids, officer=officer, admin=admin, stranger=stranger
        )
    async with AsyncSessionLocal() as session:
        users = [ids.owner, ids.admin, ids.stranger]
        await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(users)))
        await session.execute(delete(Job).where(Job.user_id.in_(users)))
        await session.execute(delete(ChatSession).where(ChatSession.user_id.in_(users)))
        await session.execute(delete(Case).where(Case.owner_id.in_(users)))
        await session.execute(delete(User).where(User.id.in_(users)))
        await session.commit()


async def _rows(actor: uuid.UUID, action: str) -> list[AuditLog]:
    async with AsyncSessionLocal() as session:
        return list(
            (
                await session.scalars(
                    select(AuditLog).where(AuditLog.user_id == actor, AuditLog.action == action)
                )
            ).all()
        )


# F-03 ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_admin_reading_a_case_leaves_a_row(world) -> None:
    response = await world.client.get(f"/cases/{world.ids.case}", headers=_bearer(world.admin))
    assert response.status_code == 200
    rows = await _rows(world.ids.admin, "admin.case.read")
    assert len(rows) == 1
    assert rows[0].resource_id == world.ids.case
    assert rows[0].metadata_["owner_id"] == str(world.ids.owner)


@pytest.mark.asyncio
async def test_an_owner_reading_their_own_case_leaves_no_admin_row(world) -> None:
    await world.client.get(f"/cases/{world.ids.case}", headers=_bearer(world.officer))
    assert await _rows(world.ids.owner, "admin.case.read") == []


@pytest.mark.asyncio
async def test_an_admin_reading_a_conversation_leaves_a_row_without_its_text(world) -> None:
    response = await world.client.get(
        f"/chat/sessions/{world.ids.chat}", headers=_bearer(world.admin)
    )
    assert response.status_code == 200
    rows = await _rows(world.ids.admin, "admin.chat_session.read")
    assert len(rows) == 1
    assert SECRET_TEXT not in json.dumps(rows[0].metadata_)


@pytest.mark.asyncio
async def test_an_admin_reading_a_job_leaves_a_row_and_the_list_shows_only_their_own(world) -> None:
    read = await world.client.get(f"/jobs/{world.ids.job}", headers=_bearer(world.admin))
    assert read.status_code == 200
    assert len(await _rows(world.ids.admin, "admin.job.read")) == 1

    listed = await world.client.get("/jobs", headers=_bearer(world.admin))
    assert listed.status_code == 200
    assert str(world.ids.job) not in {item["id"] for item in listed.json()["items"]}


@pytest.mark.asyncio
async def test_an_admin_naming_a_matter_in_a_search_leaves_a_row_without_the_query(world) -> None:
    class Empty:
        async def search_across_collections_with_timings(self, query, **kwargs):
            return [], SimpleNamespace()

    app.dependency_overrides[get_retrieval_service] = lambda: Empty()
    try:
        response = await world.client.post(
            f"/retrieval/scoped-search?mode=case_specific&case_id={world.ids.case}",
            json={"query": SECRET_TEXT, "candidate_limit": 5, "result_limit": 2},
            headers=_bearer(world.admin),
        )
    finally:
        app.dependency_overrides.pop(get_retrieval_service, None)
    assert response.status_code == 200, response.text
    rows = await _rows(world.ids.admin, "admin.case.search")
    assert len(rows) == 1
    assert SECRET_TEXT not in json.dumps(rows[0].metadata_)


# F-04 ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_admin_cannot_overwrite_another_officers_custody_dates(world) -> None:
    response = await world.client.put(
        f"/cases/{world.ids.case}/investigation/facts",
        json={"first_remand_at": "2026-01-01T10:00:00+05:30"},
        headers=_bearer(world.admin),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_an_admin_cannot_edit_another_users_case(world) -> None:
    response = await world.client.patch(
        f"/cases/{world.ids.case}", json={"title": "changed"}, headers=_bearer(world.admin)
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_an_admin_cannot_write_into_another_users_conversation(world) -> None:
    app.dependency_overrides[get_workflow] = lambda: SimpleNamespace()
    try:
        response = await world.client.post(
            "/chat/query",
            json={"query": "an admin message", "session_id": str(world.ids.chat)},
            headers=_bearer(world.admin),
        )
    finally:
        app.dependency_overrides.pop(get_workflow, None)
    assert response.status_code == 403
    async with AsyncSessionLocal() as session:
        messages = (
            await session.scalars(
                select(ChatMessage.content).where(ChatMessage.session_id == world.ids.chat)
            )
        ).all()
    assert "an admin message" not in messages


@pytest.mark.asyncio
async def test_an_admin_cannot_queue_a_review_into_another_users_conversation(world) -> None:
    response = await world.client.post(
        "/jobs/deep-review",
        json={"query": "an admin message", "session_id": str(world.ids.chat)},
        headers={**_bearer(world.admin), "Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_an_admin_naming_a_missing_case_gets_a_404_not_a_500(world) -> None:
    """F-20: the existence check sat below the administrator bypass."""
    response = await world.client.get(f"/cases/{uuid.uuid4()}", headers=_bearer(world.admin))
    assert response.status_code == 404


# F-22 ------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/cases/{case}"),
        ("get", "/cases/{case}/documents/generated"),
        ("get", "/chat/sessions/{chat}"),
        ("get", "/jobs/{job}"),
        ("post", "/jobs/{job}/cancel"),
    ],
)
async def test_a_stranger_cannot_tell_a_foreign_resource_from_a_missing_one(
    world, method: str, path: str
) -> None:
    ids = {"case": world.ids.case, "chat": world.ids.chat, "job": world.ids.job}
    foreign = await getattr(world.client, method)(
        path.format(**ids), headers=_bearer(world.stranger)
    )
    missing = await getattr(world.client, method)(
        path.format(case=uuid.uuid4(), chat=uuid.uuid4(), job=uuid.uuid4()),
        headers=_bearer(world.stranger),
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["detail"] == missing.json()["detail"]


# F-14 ------------------------------------------------------------------------


def test_a_trace_keeps_numbers_and_loses_every_string() -> None:
    trace = [
        {
            "node": "retrieval",
            "details": {
                "query": SECRET_TEXT,
                "initial_query": SECRET_TEXT,
                "topic_query": SECRET_TEXT,
                "retry": 1,
                "hits": 5,
                "rewrote": True,
                "novel_field_added_next_year": SECRET_TEXT,
            },
        }
    ]
    cleaned = trace_for_audit(trace)
    assert SECRET_TEXT not in json.dumps(cleaned)
    assert cleaned[0]["details"] == {"retry": 1, "hits": 5, "rewrote": True}


def test_old_audit_rows_are_redacted_on_the_way_out() -> None:
    stored = {
        "confidence_score": 0.4,
        "agent_trace": [{"details": {"query": SECRET_TEXT}}],
        "nested": [{"query": SECRET_TEXT, "kept": 1}],
        "previous": {"title": SECRET_TEXT},
    }
    cleaned = redact_audit_metadata(stored)
    assert SECRET_TEXT not in json.dumps(cleaned)
    assert cleaned["confidence_score"] == 0.4
    assert cleaned["nested"] == [{"kept": 1}]


@pytest.mark.asyncio
async def test_the_audit_endpoint_never_returns_query_text(world) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            AuditLog(
                user_id=world.ids.owner,
                action="chat.query",
                resource_type="chat_session",
                resource_id=world.ids.chat,
                metadata_={"agent_trace": [{"details": {"query": SECRET_TEXT}}]},
            )
        )
        await session.commit()
    response = await world.client.get("/admin/audit?limit=100", headers=_bearer(world.admin))
    assert response.status_code == 200
    assert SECRET_TEXT not in response.text


@pytest.mark.asyncio
async def test_a_case_edit_records_which_fields_not_their_values(world) -> None:
    response = await world.client.patch(
        f"/cases/{world.ids.case}", json={"title": SECRET_TEXT}, headers=_bearer(world.officer)
    )
    assert response.status_code == 200
    rows = await _rows(world.ids.owner, "case.update")
    assert rows[0].metadata_["changed_fields"] == ["title"]
    assert SECRET_TEXT not in json.dumps(rows[0].metadata_)


# F-17 ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_analysis_row_is_not_offered_as_a_draft(world) -> None:
    listed = await world.client.get(
        f"/cases/{world.ids.case}/documents/generated", headers=_bearer(world.officer)
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["documents"]] == [str(world.ids.draft)]


@pytest.mark.asyncio
async def test_opening_an_analysis_row_is_a_404_and_a_draft_still_opens(world) -> None:
    analysis = await world.client.get(
        f"/cases/{world.ids.case}/documents/generated/{world.ids.analysis}",
        headers=_bearer(world.officer),
    )
    assert analysis.status_code == 404
    draft = await world.client.get(
        f"/cases/{world.ids.case}/documents/generated/{world.ids.draft}",
        headers=_bearer(world.officer),
    )
    assert draft.status_code == 200


# F-08 ------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/ingestion/status", "/ingestion/progress"])
async def test_ingestion_routes_need_an_administrator(world, path: str) -> None:
    assert (await world.client.get(path)).status_code == 401
    assert (await world.client.get(path, headers=_bearer(world.officer))).status_code == 403


@pytest.mark.asyncio
async def test_ingestion_status_answers_an_administrator(world, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "legal_kb_root", str(tmp_path))
    response = await world.client.get("/ingestion/status", headers=_bearer(world.admin))
    assert response.status_code == 200
    assert response.json()["status"] == "not_started"


# F-07, F-15 ------------------------------------------------------------------


def test_every_filename_makes_a_latin1_safe_header() -> None:
    for name in ["प्राथमिकी.pdf", 'quo"te.pdf', "తెలుగు పత్రం.pdf", "plain.pdf", "a;b\\c.pdf"]:
        header = attachment_disposition(name)
        header.encode("latin-1")
        assert header.count('"') == 2
        assert "filename*=UTF-8''" in header


def test_the_upload_allowlist_checks_bytes_not_labels() -> None:
    assert content_matches_declared_type(b"%PDF-1.7 ...", "application/pdf")
    assert content_matches_declared_type(b"statement of the witness", "text/plain")
    assert content_matches_declared_type(b"\xff\xd8\xff\xe0 jpeg", "image/jpeg")
    assert not content_matches_declared_type(b"MZ executable", "application/pdf")
    assert not content_matches_declared_type(b"\x00\x01binary", "text/plain")
    assert not content_matches_declared_type(b"#!/bin/sh", "application/x-sh")


@pytest.mark.asyncio
async def test_an_upload_past_the_limit_or_of_the_wrong_kind_is_refused(world, monkeypatch) -> None:
    monkeypatch.setattr("app.routers.storage.MAX_INDEXABLE_BYTES", 1024)
    too_big = await world.client.post(
        f"/cases/{world.ids.case}/storage/objects",
        files={"file": ("a.txt", b"x" * 2048, "text/plain")},
        headers=_bearer(world.officer),
    )
    assert too_big.status_code == 413
    wrong_kind = await world.client.post(
        f"/cases/{world.ids.case}/storage/objects",
        files={"file": ("a.pdf", b"not a pdf", "application/pdf")},
        headers=_bearer(world.officer),
    )
    assert wrong_kind.status_code == 415


# F-10 ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registration_is_throttled_by_source_before_bcrypt(world, monkeypatch) -> None:
    await user_rate_limiter.clear()
    monkeypatch.setattr(settings, "register_requests_per_minute", 1)
    body = {"name": "A Person", "password": PASSWORD, "role": "citizen"}
    created: list[str] = []
    try:
        first = await world.client.post(
            "/auth/register", json={**body, "email": unique_email("reg")}
        )
        assert first.status_code == 201
        created.append(first.json()["user"]["id"])
        second = await world.client.post(
            "/auth/register", json={**body, "email": unique_email("reg")}
        )
        assert second.status_code == 429
        assert second.headers["Retry-After"]
    finally:
        await user_rate_limiter.clear()
        async with AsyncSessionLocal() as session:
            await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(created)))
            await session.execute(delete(User).where(User.id.in_(created)))
            await session.commit()


@pytest.mark.asyncio
async def test_sync_model_routes_share_one_bucket(world, monkeypatch) -> None:
    """Calling a different route must not buy another turn on the one slot."""
    await user_rate_limiter.clear()
    monkeypatch.setattr(settings, "llm_sync_requests_per_minute", 1)
    calls: list[str] = []

    class StubDrafting:
        def __init__(self, **_):
            pass

        async def create_fir_draft(self, **_):
            calls.append("draft")
            raise RuntimeError("stop before the model")

    monkeypatch.setattr("app.routers.documents.LegalDraftingAgent", StubDrafting)
    monkeypatch.setattr(
        app.state, "legal_rag_workflow", SimpleNamespace(retrieval=None, llm=None), raising=False
    )
    try:
        try:
            await world.client.post(
                f"/cases/{world.ids.case}/documents/draft",
                json={"case_description": "a description long enough to validate"},
                headers=_bearer(world.officer),
            )
        except RuntimeError:
            pass
        refused = await world.client.post(
            f"/cases/{world.ids.case}/documents/draft",
            json={"case_description": "a description long enough to validate"},
            headers=_bearer(world.officer),
        )
        assert refused.status_code == 429
        assert calls == ["draft"]
    finally:
        await user_rate_limiter.clear()


@pytest.mark.asyncio
async def test_retrieval_is_throttled(world, monkeypatch) -> None:
    await user_rate_limiter.clear()
    monkeypatch.setattr(settings, "retrieval_requests_per_minute", 1)

    class Empty:
        async def search(self, *args, **kwargs):
            return []

    app.dependency_overrides[get_retrieval_service] = lambda: Empty()
    body = {"query": "what is bail", "candidate_limit": 5, "result_limit": 2}
    try:
        first = await world.client.post(
            "/retrieval/search", json=body, headers=_bearer(world.officer)
        )
        second = await world.client.post(
            "/retrieval/search", json=body, headers=_bearer(world.officer)
        )
    finally:
        app.dependency_overrides.pop(get_retrieval_service, None)
        await user_rate_limiter.clear()
    assert first.status_code == 200
    assert second.status_code == 429
