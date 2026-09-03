"""The buttons rendered since the interface rebuild and sent nothing.

The table, the enum and the feedback:create permission have existed since the
initial schema; only the endpoint was missing.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.helpers import provision_test_user


pytestmark = pytest.mark.integration


async def _client() -> AsyncClient:
    from main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _answer(client: AsyncClient, headers: dict) -> dict:
    response = await client.post(
        "/chat/query",
        json={"query": "Explain the right to equality.", "response_mode": "fast"},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


async def test_feedback_is_recorded_and_a_rerating_replaces_it() -> None:
    account = await provision_test_user(
        name="Feedback One",
        email="feedback-one@example.test",
        password="Feedback-One-Password-1",
        role="citizen",
    )
    headers = {"Authorization": f"Bearer {account['access_token']}"}

    async with await _client() as client:
        answer = await _answer(client, headers)
        if not answer.get("message_id"):
            pytest.skip("this query escalated; no assistant message was persisted")
        message_id = answer["message_id"]

        first = await client.post(
            "/feedback",
            json={"message_id": message_id, "rating": "down", "correction_text": "  "},
            headers=headers,
        )
        assert first.status_code == 201
        # Whitespace-only correction text is stored as absent, not as blanks.
        assert first.json()["correction_text"] is None

        second = await client.post(
            "/feedback",
            json={"message_id": message_id, "rating": "up"},
            headers=headers,
        )
        assert second.status_code == 201
        # The unique constraint means a re-rating replaces rather than duplicates.
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["rating"] == "up"

        stored = await client.get(f"/feedback/{message_id}", headers=headers)
        assert stored.json()["rating"] == "up"


async def test_a_user_cannot_rate_another_users_answer() -> None:
    """Rating someone else's answer would corrupt the signal this collects."""
    owner = await provision_test_user(
        name="Feedback Owner",
        email="feedback-owner@example.test",
        password="Feedback-Owner-Password-1",
        role="citizen",
    )
    other = await provision_test_user(
        name="Feedback Other",
        email="feedback-other@example.test",
        password="Feedback-Other-Password-1",
        role="citizen",
    )

    async with await _client() as client:
        answer = await _answer(
            client, {"Authorization": f"Bearer {owner['access_token']}"}
        )
        if not answer.get("message_id"):
            pytest.skip("this query escalated; no assistant message was persisted")

        response = await client.post(
            "/feedback",
            json={"message_id": answer["message_id"], "rating": "up"},
            headers={"Authorization": f"Bearer {other['access_token']}"},
        )

    # 404 rather than 403: existence of another user's message is not disclosed.
    assert response.status_code == 404


async def test_a_user_question_cannot_be_rated() -> None:
    account = await provision_test_user(
        name="Feedback Role",
        email="feedback-role@example.test",
        password="Feedback-Role-Password-1",
        role="citizen",
    )
    headers = {"Authorization": f"Bearer {account['access_token']}"}

    async with await _client() as client:
        answer = await _answer(client, headers)
        session = await client.get(
            f"/chat/sessions/{answer['session_id']}", headers=headers
        )
        user_message = next(
            item for item in session.json()["messages"] if item["role"] == "user"
        )

        response = await client.post(
            "/feedback",
            json={"message_id": user_message["id"], "rating": "up"},
            headers=headers,
        )

    assert response.status_code == 422
