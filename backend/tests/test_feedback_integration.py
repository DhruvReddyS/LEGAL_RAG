"""The buttons rendered since the interface rebuild and sent nothing.

The table, the FeedbackRating enum and the feedback:create permission have
existed since the initial schema; only the endpoint was missing.

Sessions and messages are seeded directly rather than driven through
/chat/query. Feedback does not depend on how a message was produced, and
routing a rating test through retrieval and generation would make it fail for
reasons that have nothing to do with feedback.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import AsyncSessionLocal
from app.models import ChatMessage, ChatSession
from app.models.enums import ChatMessageRole
from tests.helpers import provision_test_user, unique_email


pytestmark = pytest.mark.integration


async def _client() -> AsyncClient:
    from main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_conversation(user_id: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Return (assistant_message_id, user_message_id) for a stored session."""
    async with AsyncSessionLocal() as session:
        chat_session = ChatSession(
            user_id=uuid.UUID(user_id), title="Explain the right to equality"
        )
        session.add(chat_session)
        await session.flush()

        question = ChatMessage(
            session_id=chat_session.id,
            role=ChatMessageRole.USER,
            content="Explain the right to equality.",
            citations=[],
        )
        answer = ChatMessage(
            session_id=chat_session.id,
            role=ChatMessageRole.ASSISTANT,
            content="Article 14 guarantees equality before the law [Source 1].",
            citations=[{"number": 1, "chunk_id": "gold-chunk-test"}],
        )
        session.add_all([question, answer])
        await session.commit()
        return answer.id, question.id


async def test_feedback_is_recorded_and_a_rerating_replaces_it() -> None:
    account = await provision_test_user(
        name="Feedback One",
        email=unique_email("feedback-one"),
        password="Feedback-One-Password-1",
        role="citizen",
    )
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    answer_id, _ = await _seed_conversation(account["user"]["id"])

    async with await _client() as client:
        first = await client.post(
            "/feedback",
            json={
                "message_id": str(answer_id),
                "rating": "down",
                "correction_text": "   ",
            },
            headers=headers,
        )
        assert first.status_code == 201
        # Whitespace-only correction text is stored as absent, not as blanks.
        assert first.json()["correction_text"] is None

        second = await client.post(
            "/feedback",
            json={"message_id": str(answer_id), "rating": "up"},
            headers=headers,
        )
        assert second.status_code == 201
        # The unique constraint means a re-rating replaces rather than duplicates.
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["rating"] == "up"

        stored = await client.get(f"/feedback/{answer_id}", headers=headers)
        assert stored.status_code == 200
        assert stored.json()["rating"] == "up"


async def test_a_user_cannot_rate_another_users_answer() -> None:
    """Rating someone else's answer would corrupt the signal this collects."""
    owner = await provision_test_user(
        name="Feedback Owner",
        email=unique_email("feedback-owner"),
        password="Feedback-Owner-Password-1",
        role="citizen",
    )
    other = await provision_test_user(
        name="Feedback Other",
        email=unique_email("feedback-other"),
        password="Feedback-Other-Password-1",
        role="citizen",
    )
    answer_id, _ = await _seed_conversation(owner["user"]["id"])

    async with await _client() as client:
        response = await client.post(
            "/feedback",
            json={"message_id": str(answer_id), "rating": "up"},
            headers={"Authorization": f"Bearer {other['access_token']}"},
        )

    # 404 rather than 403: the existence of another user's message is not
    # disclosed by the difference between the two.
    assert response.status_code == 404


async def test_an_admin_cannot_rate_a_citizens_answer_either() -> None:
    """Admin may read any conversation; that must not extend to rating one."""
    citizen = await provision_test_user(
        name="Feedback Citizen",
        email=unique_email("feedback-citizen"),
        password="Feedback-Citizen-Password-1",
        role="citizen",
    )
    admin = await provision_test_user(
        name="Feedback Admin",
        email=unique_email("feedback-admin"),
        password="Feedback-Admin-Password-1",
        role="admin",
    )
    answer_id, _ = await _seed_conversation(citizen["user"]["id"])

    async with await _client() as client:
        response = await client.post(
            "/feedback",
            json={"message_id": str(answer_id), "rating": "down"},
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )

    assert response.status_code == 404


async def test_a_user_question_cannot_be_rated() -> None:
    account = await provision_test_user(
        name="Feedback Role",
        email=unique_email("feedback-role"),
        password="Feedback-Role-Password-1",
        role="citizen",
    )
    _, question_id = await _seed_conversation(account["user"]["id"])

    async with await _client() as client:
        response = await client.post(
            "/feedback",
            json={"message_id": str(question_id), "rating": "up"},
            headers={"Authorization": f"Bearer {account['access_token']}"},
        )

    assert response.status_code == 422


async def test_an_unknown_message_is_not_found() -> None:
    account = await provision_test_user(
        name="Feedback Missing",
        email=unique_email("feedback-missing"),
        password="Feedback-Missing-Password-1",
        role="citizen",
    )

    async with await _client() as client:
        response = await client.post(
            "/feedback",
            json={"message_id": str(uuid.uuid4()), "rating": "up"},
            headers={"Authorization": f"Bearer {account['access_token']}"},
        )

    assert response.status_code == 404
