"""C-03, C-10 and the chat annotations, across the API boundary and the database."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import AuditLog, ChatMessage, ChatMessageAnnotation, ChatSession
from app.models.enums import ChatMessageRole
from app.routers.citizen_tools import _today, get_notice_llm
from tests.helpers import provision_test_user, unique_email

pytestmark = pytest.mark.integration


async def _client() -> AsyncClient:
    from main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _citizen() -> dict:
    account = await provision_test_user(
        name="Citizen", email=unique_email("citizen-tools"), password="password-123-long", role="citizen"
    )
    return {"auth": {"Authorization": f"Bearer {account['access_token']}"}, "id": account["user"]["id"]}


def _in(days: int) -> str:
    return (_today() + timedelta(days=days)).isoformat()


@pytest.mark.asyncio
async def test_a_deadline_belongs_to_the_person_who_wrote_it():
    owner, other = await _citizen(), await _citizen()
    async with await _client() as client:
        created = await client.post(
            "/citizen/matter/deadlines",
            headers=owner["auth"],
            json={"title": "Reply to notice", "due_on": _in(10), "provision_label": "NI s.138, proviso (c)", "source": "notice"},
        )
        assert created.status_code == 201
        row = created.json()
        assert row["provision_label"] == "NI s.138, proviso (c)"

        assert (await client.get("/citizen/matter/deadlines", headers=other["auth"])).json()["items"] == []
        path = f"/citizen/matter/deadlines/{row['id']}"
        assert (await client.patch(path, headers=other["auth"], json={"title": "stolen"})).status_code == 404
        assert (await client.delete(path, headers=other["auth"])).status_code == 404

        mine = (await client.get("/citizen/matter/deadlines", headers=owner["auth"])).json()["items"]
        assert [item["title"] for item in mine] == ["Reply to notice"]


@pytest.mark.asyncio
async def test_the_list_says_what_is_overdue_soon_and_later_in_date_order():
    user = await _citizen()
    async with await _client() as client:
        for title, days in (("later", 60), ("late", -2), ("soon", 3), ("today", 0)):
            response = await client.post(
                "/citizen/matter/deadlines",
                headers=user["auth"],
                json={"title": title, "due_on": _in(days), "remind_days_before": 7},
            )
            assert response.status_code == 201
        items = (await client.get("/citizen/matter/deadlines", headers=user["auth"])).json()["items"]
    assert [(item["title"], item["status"]) for item in items] == [
        ("late", "overdue"),
        ("today", "due_today"),
        ("soon", "due_soon"),
        ("later", "upcoming"),
    ]
    assert items[0]["days_left"] == -2


@pytest.mark.asyncio
async def test_completing_a_date_moves_it_to_done_and_undoing_it_restores_it():
    user = await _citizen()
    async with await _client() as client:
        first = (await client.post("/citizen/matter/deadlines", headers=user["auth"], json={"title": "a", "due_on": _in(1)})).json()
        await client.post("/citizen/matter/deadlines", headers=user["auth"], json={"title": "b", "due_on": _in(2)})
        done = await client.patch(f"/citizen/matter/deadlines/{first['id']}", headers=user["auth"], json={"completed": True})
        assert done.json()["status"] == "done"
        items = (await client.get("/citizen/matter/deadlines", headers=user["auth"])).json()["items"]
        assert [item["title"] for item in items] == ["b", "a"], "finished dates sort last"
        undone = await client.patch(f"/citizen/matter/deadlines/{first['id']}", headers=user["auth"], json={"completed": False})
        assert undone.json()["status"] == "due_soon"


@pytest.mark.asyncio
async def test_a_deleted_date_is_gone_from_the_database():
    user = await _citizen()
    async with await _client() as client:
        row = (await client.post("/citizen/matter/deadlines", headers=user["auth"], json={"title": "x", "due_on": _in(1)})).json()
        assert (await client.delete(f"/citizen/matter/deadlines/{row['id']}", headers=user["auth"])).status_code == 204
        assert (await client.get("/citizen/matter/deadlines", headers=user["auth"])).json()["items"] == []


@pytest.mark.asyncio
async def test_a_blank_title_and_a_bad_reminder_are_refused():
    user = await _citizen()
    async with await _client() as client:
        blank = await client.post("/citizen/matter/deadlines", headers=user["auth"], json={"title": "   ", "due_on": _in(1)})
        assert blank.status_code == 422
        bad = await client.post(
            "/citizen/matter/deadlines", headers=user["auth"], json={"title": "t", "due_on": _in(1), "remind_days_before": 900}
        )
        assert bad.status_code == 422


@pytest.mark.asyncio
async def test_deadlines_need_an_account():
    async with await _client() as client:
        assert (await client.get("/citizen/matter/deadlines")).status_code == 401
        assert (await client.post("/citizen/tools/notice/explain", json={"text": "x"})).status_code == 401


@pytest.mark.asyncio
async def test_explaining_a_notice_leaves_only_its_type_in_the_audit_log():
    user = await _citizen()
    secret = "Ramesh Kumar of 14 Lake View Road"
    text = f"SUMMONS. In the Court of the Magistrate. {secret} is required to appear on 3/2/2026."
    async with await _client() as client:
        response = await client.post("/citizen/tools/notice/explain", headers=user["auth"], json={"text": text})
    assert response.status_code == 200
    body = response.json()
    assert body["notice_type"] == "court_summons"
    assert body["plain_status"] == "not_requested"
    async with AsyncSessionLocal() as session:
        rows = (
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.user_id == uuid.UUID(user["id"]), AuditLog.action == "citizen.notice_explain"
                )
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].metadata_ == {"notice_type": "court_summons", "plain_status": "not_requested"}


@pytest.mark.asyncio
async def test_plain_language_uses_the_model_and_a_failure_still_returns_the_reading():
    from main import app

    class Down:
        async def structured(self, *args, **kwargs):
            raise RuntimeError("model unavailable")

    app.dependency_overrides[get_notice_llm] = lambda: Down()
    try:
        user = await _citizen()
        async with await _client() as client:
            response = await client.post(
                "/citizen/tools/notice/explain",
                headers=user["auth"],
                json={"text": "You are under digital arrest.", "plain_language": True, "language": "te"},
            )
    finally:
        app.dependency_overrides.pop(get_notice_llm, None)
    assert response.status_code == 200
    body = response.json()
    assert body["plain"] is None and body["plain_status"] == "unavailable"
    assert body["abstained"] is True and body["flags"]


@pytest.mark.asyncio
async def test_a_reopened_answer_keeps_its_grades_and_its_safety_label():
    user = await _citizen()
    grades = [{"section": "Why", "confidence": "strong", "reason": "two sources"}]
    async with AsyncSessionLocal() as session:
        chat = ChatSession(user_id=uuid.UUID(user["id"]), title="t")
        session.add(chat)
        await session.flush()
        graded = ChatMessage(session_id=chat.id, role=ChatMessageRole.ASSISTANT, content="answer", citations=[])
        safety = ChatMessage(session_id=chat.id, role=ChatMessageRole.ASSISTANT, content="call 112", citations=[])
        plain = ChatMessage(session_id=chat.id, role=ChatMessageRole.ASSISTANT, content="old", citations=[])
        session.add_all([graded, safety, plain])
        await session.flush()
        session.add(ChatMessageAnnotation(message_id=graded.id, section_confidence=grades))
        session.add(ChatMessageAnnotation(message_id=safety.id, safety_kind="emergency"))
        await session.commit()
        chat_id = chat.id
    async with await _client() as client:
        response = await client.get(f"/chat/sessions/{chat_id}", headers=user["auth"])
    rows = {row["content"]: row for row in response.json()["messages"]}
    assert rows["answer"]["section_confidence"] == grades
    assert rows["call 112"]["safety_kind"] == "emergency"
    assert rows["old"]["section_confidence"] == [] and rows["old"]["safety_kind"] is None


@pytest.mark.asyncio
async def test_a_safety_answer_through_the_real_route_is_annotated():
    from main import app

    # Screened before any pipeline runs, so a stand-in is never called.
    if not hasattr(app.state, "legal_rag_workflow"):
        app.state.legal_rag_workflow = object()
    user = await _citizen()
    async with await _client() as client:
        response = await client.post(
            "/chat/query", headers=user["auth"], json={"query": "I want to kill myself", "response_mode": "auto"}
        )
        assert response.status_code == 200
        assert response.json()["routing_reason"].startswith("safety_")
        stored = await client.get(f"/chat/sessions/{response.json()['session_id']}", headers=user["auth"])
    answer = [row for row in stored.json()["messages"] if row["role"] == "assistant"][0]
    assert answer["safety_kind"] == "emergency"


@pytest.mark.asyncio
async def test_sessions_can_be_listed_per_case():
    user = await _citizen()
    other_case = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        session.add(ChatSession(user_id=uuid.UUID(user["id"]), title="law only"))
        await session.commit()
    async with await _client() as client:
        everything = await client.get("/chat/sessions", headers=user["auth"])
        filtered = await client.get(f"/chat/sessions?case_id={other_case}", headers=user["auth"])
    assert len(everything.json()["items"]) == 1
    assert filtered.json()["items"] == []
