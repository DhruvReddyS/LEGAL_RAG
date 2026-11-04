"""Deleting a chat erases it from the server, and only its owner can."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.core.database import AsyncSessionLocal
from app.models import ChatMessage, ChatSession, User
from app.models.enums import ChatMessageRole
from main import app


async def _register(client: AsyncClient, suffix: str, index: int) -> tuple[uuid.UUID, dict[str, str]]:
    response = await client.post(
        "/auth/register",
        json={
            "name": f"Chat User {index}",
            "email": f"chat-{index}-{suffix}@example.com",
            "password": "CorrectHorseBattery99!",
            "role": "citizen",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return uuid.UUID(body["user"]["id"]), {"Authorization": f"Bearer {body['access_token']}"}


async def _session_with_a_message(user_id: uuid.UUID) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        chat = ChatSession(user_id=user_id, title="A private question")
        session.add(chat)
        await session.flush()
        session.add(
            ChatMessage(session_id=chat.id, role=ChatMessageRole.USER, content="A private question", citations=[])
        )
        await session.commit()
        return chat.id


@pytest.mark.asyncio
async def test_a_chat_can_be_renamed_and_deleted_by_its_owner_only() -> None:
    suffix = uuid.uuid4().hex[:8]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        owner_id, owner = await _register(client, suffix, 1)
        other_id, other = await _register(client, suffix, 2)
        chat_id = await _session_with_a_message(owner_id)
        try:
            assert (await client.delete(f"/chat/sessions/{chat_id}", headers=other)).status_code in {403, 404}
            assert (
                await client.patch(f"/chat/sessions/{chat_id}", headers=other, json={"title": "Taken"})
            ).status_code in {403, 404}

            renamed = await client.patch(f"/chat/sessions/{chat_id}", headers=owner, json={"title": "Renamed"})
            assert renamed.status_code == 200, renamed.text
            assert renamed.json()["title"] == "Renamed"

            deleted = await client.delete(f"/chat/sessions/{chat_id}", headers=owner)
            assert deleted.status_code == 204, deleted.text
            assert (await client.get(f"/chat/sessions/{chat_id}", headers=owner)).status_code == 404

            async with AsyncSessionLocal() as session:
                assert (
                    await session.scalar(
                        select(func.count(ChatMessage.id)).where(ChatMessage.session_id == chat_id)
                    )
                ) == 0, "deleting a chat must erase its messages"
        finally:
            async with AsyncSessionLocal() as session:
                await session.execute(delete(User).where(User.id.in_((owner_id, other_id))))
                await session.commit()
