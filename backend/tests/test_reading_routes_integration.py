"""The routes that release their session before a slow model call.

Reading the user after that release raised on every request, and tests of the logic
behind these routes could not see it, so these go through the routes themselves.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import AsyncSessionLocal
from app.models import ChatMessage, ChatSession
from app.models.enums import ChatMessageRole
from app.services import answer_translation
from app.services.case_insights import _Conflicts, _People, _Person
from main import app
from tests.helpers import provision_test_user, unique_email

pytestmark = pytest.mark.integration

STATEMENT = "Ramesh Kumar stated that he saw the accused on 10 March 2024."
ANSWER = "File within 30 days [Source 1]."
TRANSLATED = "30 दिनों में दाखिल करें [Source 1]।"


class _Model:
    async def structured(self, prompt, schema, **kwargs):
        if schema is _People:
            return _People(people=[_Person(name="Ramesh Kumar", role="witness", quote="Ramesh Kumar stated that he saw")])
        return _Conflicts()

    async def generate_with_metrics(self, prompt, *, num_predict=900):
        return TRANSLATED, {}


class _Store:
    async def scroll(self, **kwargs):
        point = SimpleNamespace(payload={"text": STATEMENT, "title": "A.pdf", "document_id": "d", "page_start": 1, "page_end": 1})
        return [point], None


@pytest.fixture(autouse=True)
def _services(monkeypatch):
    monkeypatch.setattr(app.state, "legal_rag_workflow", SimpleNamespace(llm=_Model()), raising=False)
    monkeypatch.setattr(app.state, "retrieval_service", SimpleNamespace(client=_Store()), raising=False)
    answer_translation._cache.clear()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _account(role: str) -> dict:
    return await provision_test_user(name="Reader", email=unique_email("reading"), password="Reading-Test-Passw0rd!", role=role)


def _bearer(account: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {account['access_token']}"}


async def _message(account: dict, citations: list) -> uuid.UUID:
    async with _client() as client:
        me = await client.get("/auth/me", headers=_bearer(account))
    async with AsyncSessionLocal() as session:
        chat = ChatSession(user_id=uuid.UUID(me.json()["id"]), title="Test")
        session.add(chat)
        await session.flush()
        message = ChatMessage(session_id=chat.id, role=ChatMessageRole.ASSISTANT, content=ANSWER, citations=citations)
        session.add(message)
        await session.commit()
        return message.id


async def _case(client: AsyncClient, account: dict) -> str:
    response = await client.post("/cases", json={"title": "Reading test"}, headers=_bearer(account))
    assert response.status_code == 201
    return response.json()["id"]


async def test_the_owner_gets_a_translation() -> None:
    account = await _account("citizen")
    message = await _message(account, [{"number": 1}])
    async with _client() as client:
        response = await client.post(f"/chat/messages/{message}/translation", json={"language": "hi"}, headers=_bearer(account))
    assert response.status_code == 200
    assert response.json()["text"] == TRANSLATED


async def test_another_users_answer_is_not_found() -> None:
    owner, other = await _account("citizen"), await _account("citizen")
    message = await _message(owner, [{"number": 1}])
    async with _client() as client:
        response = await client.post(f"/chat/messages/{message}/translation", json={"language": "hi"}, headers=_bearer(other))
    assert response.status_code == 404


async def test_an_answer_with_no_sources_is_not_translated() -> None:
    account = await _account("citizen")
    message = await _message(account, [])
    async with _client() as client:
        response = await client.post(f"/chat/messages/{message}/translation", json={"language": "hi"}, headers=_bearer(account))
    assert response.status_code == 422


async def test_the_owner_reads_people_conflicts_and_the_timeline() -> None:
    account = await _account("advocate")
    async with _client() as client:
        case_id = await _case(client, account)
        people = await client.post(f"/cases/{case_id}/insights/people", headers=_bearer(account))
        conflicts = await client.post(f"/cases/{case_id}/insights/conflicts", headers=_bearer(account))
        timeline = await client.get(f"/cases/{case_id}/chronology", headers=_bearer(account))
    assert people.status_code == 200
    assert people.json()["items"][0]["name"] == "Ramesh Kumar"
    assert conflicts.status_code == 200
    assert timeline.json()["events"][0]["date"] == "2024-03-10"


async def test_another_advocate_cannot_read_the_case() -> None:
    owner, other = await _account("advocate"), await _account("advocate")
    async with _client() as client:
        case_id = await _case(client, owner)
        insights = await client.post(f"/cases/{case_id}/insights/people", headers=_bearer(other))
        timeline = await client.get(f"/cases/{case_id}/chronology", headers=_bearer(other))
    assert insights.status_code in (403, 404)
    assert timeline.status_code in (403, 404)
