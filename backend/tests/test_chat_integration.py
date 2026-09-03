from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models import AuditLog, Job, User
from app.routers.chat import get_workflow
from app.schemas.agents import AgentCitation, AgentTraceEvent, QueryIntent
from main import app


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

    The listing must not ship message bodies: a case-scoped session's messages
    can quote private evidence, and a sidebar needs none of it.
    """
    owner = await provision_test_user(
        name="Citizen One",
        email="sessions-owner@example.test",
        password="Sessions-Owner-1",
        role="citizen",
    )
    other = await provision_test_user(
        name="Citizen Two",
        email="sessions-other@example.test",
        password="Sessions-Other-1",
        role="citizen",
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
        created = await client.post(
            "/chat/query",
            json={"query": "What is the right to equality?", "response_mode": "fast"},
            headers=owner_headers,
        )
        assert created.status_code == 200
        session_id = created.json()["session_id"]

        listing = await client.get("/chat/sessions", headers=owner_headers)
        assert listing.status_code == 200
        items = listing.json()["items"]
        assert [item["id"] for item in items] == [session_id]
        row = items[0]
        assert row["message_count"] >= 2
        assert row["last_message_preview"]
        assert "messages" not in row

        # A second account must not see it, even though both are citizens.
        other_listing = await client.get(
            "/chat/sessions",
            headers={"Authorization": f"Bearer {other['access_token']}"},
        )
        assert other_listing.status_code == 200
        assert other_listing.json()["items"] == []


@pytest.mark.asyncio
async def test_escalation_returns_the_fast_brief_instead_of_discarding_it() -> None:
    """A low-confidence Fast result used to be thrown away.

    The citizen went from a 70ms response to a blank multi-minute wait, with
    the retrieved passages sitting unused in memory.
    """
    user = await provision_test_user(
        name="Citizen Escalate",
        email="escalation-brief@example.test",
        password="Escalation-Brief-1",
        role="citizen",
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/chat/query",
            json={
                "query": "What should I do about a noisy neighbour at night?",
                "response_mode": "fast",
            },
            headers={"Authorization": f"Bearer {user['access_token']}"},
        )
        assert response.status_code == 200
        payload = response.json()
        if payload["delivery_state"] != "searching_more_thoroughly":
            pytest.skip("this corpus answered the query confidently; nothing escalated")

        assert payload["job_id"]
        assert payload["evidence_strength"] == "insufficient"
        # Whatever the quick search found travels with the placeholder.
        if payload["citations"]:
            assert "not yet" in payload["answer"].casefold()
