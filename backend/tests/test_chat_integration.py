from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models import AuditLog, ChatMessage, ChatSession, Job, User
from app.models.enums import ChatMessageRole
from app.routers.chat import get_workflow
from app.schemas.agents import AgentCitation, AgentTraceEvent, QueryIntent
from main import app
from tests.helpers import provision_test_user, unique_email


class FakeWorkflow:
    async def run(self, **_: object) -> dict:
        return {
            "final_answer": "FIR registration is mandatory for a cognizable offence [Source 1].",
            "citations": [
                AgentCitation(
                    number=1,
                    chunk_id="gold-chunk-test",
                    title="Official FIR Advisory",
                    source_type="government_guidance",
                    page_start=1,
                    page_end=2,
                    excerpt="Registration is mandatory.",
                )
            ],
            "confidence_score": 0.9,
            "evidence_strength": "strong",
            "intent": QueryIntent(retrieval_query="mandatory FIR registration"),
            "agent_trace": [AgentTraceEvent(node="verification", details={"score": 0.9})],
        }


class FakeFastResearch:
    def __init__(self, confidence: float) -> None:
        self.confidence = confidence

    async def run(self, **_: object) -> dict:
        return {
            "final_answer": "A retrieval-only preview that must not be shown when weak.",
            "citations": [],
            "confidence_score": self.confidence,
            "evidence_strength": "moderate" if self.confidence >= 0.6 else "insufficient",
            "intent": QueryIntent(retrieval_query="test query"),
            "agent_trace": [AgentTraceEvent(node="fast_retrieval", details={"score": self.confidence})],
            "timings": {"workflow_total_ms": 1.25},
        }


@pytest.mark.asyncio
async def test_chat_persistence_and_session_ownership() -> None:
    suffix = uuid.uuid4().hex
    password = "CorrectHorseBattery99!"
    user_ids: list[uuid.UUID] = []
    session_id: uuid.UUID | None = None
    app.dependency_overrides[get_workflow] = lambda: FakeWorkflow()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            tokens: list[str] = []
            for index in range(2):
                response = await client.post(
                    "/auth/register",
                    json={
                        "name": f"Chat User {index}",
                        "email": f"chat-{index}-{suffix}@example.com",
                        "password": password,
                        "role": "citizen",
                    },
                )
                assert response.status_code == 201, response.text
                body = response.json()
                user_ids.append(uuid.UUID(body["user"]["id"]))
                tokens.append(body["access_token"])

            created = await client.post(
                "/chat/query",
                headers={"Authorization": f"Bearer {tokens[0]}"},
                json={"query": "When is FIR registration mandatory?"},
            )
            assert created.status_code == 200, created.text
            body = created.json()
            session_id = uuid.UUID(body["session_id"])
            assert body["confidence_score"] == 0.9
            assert body["citations"][0]["chunk_id"] == "gold-chunk-test"

            history = await client.get(
                f"/chat/sessions/{session_id}",
                headers={"Authorization": f"Bearer {tokens[0]}"},
            )
            assert history.status_code == 200, history.text
            assert [item["role"] for item in history.json()["messages"]] == ["user", "assistant"]

            denied = await client.get(
                f"/chat/sessions/{session_id}",
                headers={"Authorization": f"Bearer {tokens[1]}"},
            )
            assert denied.status_code == 403

            async with AsyncSessionLocal() as session:
                audit = await session.scalar(
                    select(AuditLog).where(
                        AuditLog.user_id == user_ids[0],
                        AuditLog.action == "chat.query",
                    )
                )
                assert audit is not None
                assert audit.metadata_["agent_trace"][0]["node"] == "verification"
    finally:
        app.dependency_overrides.pop(get_workflow, None)
        async with AsyncSessionLocal() as session:
            if user_ids:
                await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
                await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()


@pytest.mark.asyncio
async def test_low_confidence_fast_result_is_hidden_and_auto_escalated() -> None:
    suffix = uuid.uuid4().hex
    user_ids: list[uuid.UUID] = []
    original_fast = getattr(app.state, "fast_research_service", None)
    app.state.fast_research_service = FakeFastResearch(0.2)
    app.dependency_overrides[get_workflow] = lambda: FakeWorkflow()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/auth/register",
                json={
                    "name": "Escalation User",
                    "email": f"escalate-{suffix}@example.com",
                    "password": "CorrectHorseBattery99!",
                    "role": "citizen",
                },
            )
            body = response.json()
            user_ids.append(uuid.UUID(body["user"]["id"]))
            created = await client.post(
                "/chat/query",
                headers={"Authorization": f"Bearer {body['access_token']}"},
                json={"query": "An intentionally weak source match", "response_mode": "fast"},
            )
            assert created.status_code == 200, created.text
            result = created.json()
            assert result["delivery_state"] == "searching_more_thoroughly"
            assert result["response_mode"] == "deep"
            assert result["citations"] == []
            assert result["message_id"] is None
            assert result["job_id"] is not None
            assert result["confidence_score"] == 0.2

            async with AsyncSessionLocal() as session:
                job = await session.get(Job, uuid.UUID(result["job_id"]))
                assert job is not None
                assert job.payload["auto_escalated_from_fast"] is True
                assert job.payload["fast_confidence_score"] == 0.2
    finally:
        if original_fast is None:
            del app.state.fast_research_service
        else:
            app.state.fast_research_service = original_fast
        app.dependency_overrides.pop(get_workflow, None)
        async with AsyncSessionLocal() as session:
            if user_ids:
                await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
                await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()


@pytest.mark.asyncio
async def test_strong_fast_result_is_not_auto_escalated() -> None:
    suffix = uuid.uuid4().hex
    user_ids: list[uuid.UUID] = []
    original_fast = getattr(app.state, "fast_research_service", None)
    app.state.fast_research_service = FakeFastResearch(0.8)
    app.dependency_overrides[get_workflow] = lambda: FakeWorkflow()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/auth/register",
                json={
                    "name": "Strong Fast User",
                    "email": f"strong-{suffix}@example.com",
                    "password": "CorrectHorseBattery99!",
                    "role": "citizen",
                },
            )
            body = response.json()
            user_ids.append(uuid.UUID(body["user"]["id"]))
            created = await client.post(
                "/chat/query",
                headers={"Authorization": f"Bearer {body['access_token']}"},
                json={"query": "Article 14 equality", "response_mode": "fast"},
            )
            assert created.status_code == 200, created.text
            result = created.json()
            assert result["delivery_state"] == "complete"
            assert result["response_mode"] == "fast"
            assert result["job_id"] is None
            assert result["message_id"] is not None
    finally:
        if original_fast is None:
            del app.state.fast_research_service
        else:
            app.state.fast_research_service = original_fast
        app.dependency_overrides.pop(get_workflow, None)
        async with AsyncSessionLocal() as session:
            if user_ids:
                await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
                await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()


@pytest.mark.asyncio
async def test_chat_sessions_list_is_owner_scoped_and_carries_no_message_bodies() -> None:
    """History lived in sessionStorage because nothing could list it back.

    Sessions are seeded directly: the listing does not depend on how a
    conversation was produced, and driving it through retrieval would make it
    fail for reasons unrelated to listing.
    """
    owner = await provision_test_user(
        name="Sessions Owner",
        email=unique_email("sessions-owner"),
        password="Sessions-Owner-Password-1",
        role="citizen",
    )
    other = await provision_test_user(
        name="Sessions Other",
        email=unique_email("sessions-other"),
        password="Sessions-Other-Password-1",
        role="citizen",
    )

    async with AsyncSessionLocal() as session:
        chat_session = ChatSession(
            user_id=uuid.UUID(owner["user"]["id"]),
            title="What is the right to equality?",
        )
        session.add(chat_session)
        await session.flush()
        session.add_all(
            [
                ChatMessage(
                    session_id=chat_session.id,
                    role=ChatMessageRole.USER,
                    content="What is the right to equality?",
                    citations=[],
                ),
                ChatMessage(
                    session_id=chat_session.id,
                    role=ChatMessageRole.ASSISTANT,
                    content="Article 14 guarantees equality before the law.",
                    citations=[],
                ),
            ]
        )
        await session.commit()
        session_id = str(chat_session.id)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        listing = await client.get(
            "/chat/sessions",
            headers={"Authorization": f"Bearer {owner['access_token']}"},
        )
        assert listing.status_code == 200
        rows = listing.json()["items"]
        row = next(item for item in rows if item["id"] == session_id)
        assert row["message_count"] == 2
        assert row["last_message_preview"].startswith("Article 14")
        # A sidebar row must not ship message bodies: a case-scoped session's
        # messages can quote private evidence.
        assert "messages" not in row

        # A second citizen must not see it.
        other_listing = await client.get(
            "/chat/sessions",
            headers={"Authorization": f"Bearer {other['access_token']}"},
        )
        assert all(item["id"] != session_id for item in other_listing.json()["items"])


@pytest.mark.asyncio
async def test_escalation_returns_the_fast_brief_instead_of_discarding_it() -> None:
    """A low-confidence Fast result used to be thrown away.

    The citizen went from a fast response to a blank multi-minute wait with the
    retrieved passages sitting unused in memory.
    """
    account = await provision_test_user(
        name="Escalation Brief",
        email=unique_email("escalation-brief"),
        password="Escalation-Brief-Password-1",
        role="citizen",
    )

    original_fast = getattr(app.state, "fast_research_service", None)
    app.state.fast_research_service = FakeFastResearch(0.2)
    app.dependency_overrides[get_workflow] = lambda: FakeWorkflow()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/chat/query",
                json={"query": "Is FIR registration mandatory?", "response_mode": "fast"},
                headers={"Authorization": f"Bearer {account['access_token']}"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["delivery_state"] == "searching_more_thoroughly"
        assert payload["job_id"]
        assert payload["evidence_strength"] == "insufficient"
        # The placeholder says plainly that a longer check is running.
        assert "more thoroughly" in payload["answer"].casefold()

        # Escalation enqueues a real job. Left QUEUED it would be claimed by
        # whichever worker test runs next, which is how the jobs suite started
        # failing only when run after this one.
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(Job).where(Job.id == uuid.UUID(payload["job_id"]))
            )
            await session.commit()
    finally:
        if original_fast is None:
            del app.state.fast_research_service
        else:
            app.state.fast_research_service = original_fast
        app.dependency_overrides.pop(get_workflow, None)
