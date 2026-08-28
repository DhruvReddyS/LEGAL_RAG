from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models import AuditLog, User
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
