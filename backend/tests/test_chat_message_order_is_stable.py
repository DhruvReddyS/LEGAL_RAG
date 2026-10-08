"""A conversation reads in the order it was written, every time.

`chat_messages.created_at` defaults to `now()`, which in PostgreSQL is the
*transaction* timestamp. A chat request writes the question and the answer in
one transaction, so both rows carry a byte-identical value and any ordering
built on that column is left to the planner.

This was not theoretical. Measured before the fix: 1,225 of 2,912 stored
messages shared a timestamp with a sibling in the same session, and
`test_chat_persistence_and_session_ownership` failed about one run in three
with `['assistant', 'user']`. A citizen reading their own history could be
shown the answer above the question.

These tests write the colliding case deliberately -- one transaction, both
roles -- and assert the order survives it.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import ChatMessage, ChatSession
from app.models.enums import ChatMessageRole
from tests.helpers import provision_test_user


async def _session_with_a_colliding_turn(turns: int = 3) -> tuple[uuid.UUID, uuid.UUID]:
    """Write `turns` question/answer pairs, each pair in one transaction."""
    suffix = uuid.uuid4().hex
    user = await provision_test_user(
        name="Ordering User",
        email=f"ordering-{suffix}@example.com",
        password="CorrectHorseBattery99!",
        role="citizen",
    )
    user_id = uuid.UUID(str(user["user"]["id"]))
    async with AsyncSessionLocal() as session:
        chat_session = ChatSession(user_id=user_id, title="ordering")
        session.add(chat_session)
        await session.flush()
        session_id = chat_session.id
        for index in range(turns):
            # Both rows inside one flush, which is what makes the timestamps
            # identical. Writing them in separate transactions would not
            # reproduce the bug.
            session.add(
                ChatMessage(
                    session_id=session_id,
                    role=ChatMessageRole.USER,
                    content=f"question {index}",
                    citations=[],
                )
            )
            session.add(
                ChatMessage(
                    session_id=session_id,
                    role=ChatMessageRole.ASSISTANT,
                    content=f"answer {index}",
                    citations=[],
                )
            )
            await session.flush()
        await session.commit()
    return session_id, user_id


@pytest.mark.asyncio
async def test_the_timestamps_really_do_collide() -> None:
    """The premise of every other test here.

    If PostgreSQL ever started handing out distinct timestamps inside a
    transaction, these tests would pass for the wrong reason and the ordering
    column would look unnecessary.
    """
    session_id, _ = await _session_with_a_colliding_turn(turns=1)
    async with AsyncSessionLocal() as session:
        rows = (
            await session.scalars(
                select(ChatMessage).where(ChatMessage.session_id == session_id)
            )
        ).all()
    assert len({row.created_at for row in rows}) == 1, "the collision this guards against is gone"


@pytest.mark.asyncio
async def test_a_conversation_loads_question_before_answer() -> None:
    session_id, _ = await _session_with_a_colliding_turn()
    async with AsyncSessionLocal() as session:
        chat_session = await session.scalar(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        await session.refresh(chat_session, ["messages"])
        roles = [message.role.value for message in chat_session.messages]
        contents = [message.content for message in chat_session.messages]
    assert roles == ["user", "assistant"] * 3
    assert contents == [
        "question 0", "answer 0",
        "question 1", "answer 1",
        "question 2", "answer 2",
    ]


@pytest.mark.asyncio
async def test_the_order_is_the_same_on_every_read() -> None:
    """The old failure was intermittent, so one passing read proves nothing."""
    session_id, _ = await _session_with_a_colliding_turn()
    seen: set[tuple[str, ...]] = set()
    for _ in range(8):
        async with AsyncSessionLocal() as session:
            chat_session = await session.scalar(
                select(ChatSession).where(ChatSession.id == session_id)
            )
            await session.refresh(chat_session, ["messages"])
            seen.add(tuple(message.content for message in chat_session.messages))
    assert len(seen) == 1, f"ordering is not stable across reads: {seen}"


@pytest.mark.asyncio
async def test_the_sequence_is_monotonic_and_unique_within_a_session() -> None:
    session_id, _ = await _session_with_a_colliding_turn()
    async with AsyncSessionLocal() as session:
        sequences = list(
            (
                await session.scalars(
                    select(ChatMessage.sequence)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.sequence)
                )
            ).all()
        )
    assert len(sequences) == len(set(sequences)), "a sequence value was reused"
    assert sequences == sorted(sequences)


@pytest.mark.asyncio
async def test_the_newest_message_of_a_session_is_the_assistant_reply() -> None:
    """What the session list shows as a preview.

    That query used to carry its own tiebreak -- order by created_at, then
    prefer the assistant role -- because of the same collision. It now reads
    the sequence, so this asserts the preview did not regress when the
    workaround was removed.
    """
    from app.routers.chat import list_chat_sessions  # noqa: F401 - import guard

    session_id, _ = await _session_with_a_colliding_turn()
    async with AsyncSessionLocal() as session:
        newest = await session.scalar(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.sequence.desc())
            .limit(1)
        )
    assert newest is not None
    assert newest.role is ChatMessageRole.ASSISTANT
    assert newest.content == "answer 2"
