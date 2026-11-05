"""The daily retention pass: off at 0, single instance, audited, and unable to kill the app."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, update

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import AuditLog, ChatMessage, ChatSession
from app.models.admin_tools import RetentionPolicy
from app.models.enums import ChatMessageRole
from app.services import privacy, scheduled_passes
from tests.helpers import provision_test_user, unique_email

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def _no_earlier_pass():
    async with AsyncSessionLocal() as session:
        await session.execute(delete(AuditLog).where(AuditLog.action == scheduled_passes.RETENTION_PASS_ACTION))
        await session.commit()
    yield


async def _conversation(age_days: int) -> uuid.UUID:
    body = await provision_test_user(
        name="Asha Rao", email=unique_email("retain"), password="Original-Password-1234", role="citizen"
    )
    old = datetime.now(timezone.utc) - timedelta(days=age_days)
    async with AsyncSessionLocal() as session:
        chat = ChatSession(user_id=uuid.UUID(body["user"]["id"]), title="A chat", created_at=old)
        session.add(chat)
        await session.flush()
        session.add(
            ChatMessage(session_id=chat.id, role=ChatMessageRole.USER, content="Hello", citations=[], created_at=old)
        )
        await session.commit()
        return chat.id


async def _exists(chat_id: uuid.UUID) -> bool:
    async with AsyncSessionLocal() as session:
        return await session.get(ChatSession, chat_id) is not None


async def _pass_rows() -> list[AuditLog]:
    async with AsyncSessionLocal() as session:
        return list(
            (await session.scalars(select(AuditLog).where(AuditLog.action == scheduled_passes.RETENTION_PASS_ACTION))).all()
        )


async def test_it_is_off_at_the_default_and_keeps_everything(monkeypatch) -> None:
    monkeypatch.setattr(settings, "chat_retention_days", 0)
    chat = await _conversation(age_days=4000)
    assert await scheduled_passes.run_retention_pass() == {"status": "off"}
    assert await _exists(chat)
    assert await _pass_rows() == [], "off means no run at all, so nothing to record"


async def test_it_applies_the_configured_period_and_audits_the_run(monkeypatch) -> None:
    monkeypatch.setattr(settings, "chat_retention_days", 30)
    old, recent = await _conversation(age_days=45), await _conversation(age_days=5)

    outcome = await scheduled_passes.run_retention_pass()

    assert outcome["status"] == "ran" and outcome["erased"] >= 1
    assert not await _exists(old)
    assert await _exists(recent)
    rows = await _pass_rows()
    assert len(rows) == 1 and rows[0].metadata_["days"] == 30
    assert rows[0].metadata_["erased"] == outcome["erased"]


async def test_a_pass_that_ran_recently_is_not_run_again(monkeypatch) -> None:
    monkeypatch.setattr(settings, "chat_retention_days", 30)
    assert (await scheduled_passes.run_retention_pass())["status"] == "ran"
    old = await _conversation(age_days=45)
    assert await scheduled_passes.run_retention_pass() == {"status": "not_due"}
    assert await _exists(old), "a restart or a second instance does not repeat today's pass"

    tomorrow = datetime.now(timezone.utc) + scheduled_passes.PASS_INTERVAL + timedelta(minutes=1)
    assert (await scheduled_passes.run_retention_pass(now=tomorrow))["status"] == "ran"
    assert not await _exists(old)


async def test_a_second_instance_stands_aside_while_the_lock_is_held(monkeypatch) -> None:
    monkeypatch.setattr(settings, "chat_retention_days", 30)
    old = await _conversation(age_days=45)
    async with AsyncSessionLocal() as holder:
        assert await holder.scalar(select(func.pg_try_advisory_xact_lock(scheduled_passes.RETENTION_LOCK_KEY)))
        assert await scheduled_passes.run_retention_pass() == {"status": "locked"}
        await holder.rollback()
    assert await _exists(old)
    assert (await scheduled_passes.run_retention_pass())["status"] == "ran"


async def test_a_failed_pass_rolls_back_is_logged_and_does_not_raise(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "chat_retention_days", 30)
    old = await _conversation(age_days=45)

    async def fails(session, *, days=None):
        await session.execute(delete(ChatSession))
        raise RuntimeError("private detail that must not reach the log")

    monkeypatch.setattr(privacy, "apply_retention", fails)
    with caplog.at_level(logging.ERROR, logger="legal_rag.scheduled"):
        assert await scheduled_passes.run_guarded("retention", scheduled_passes.run_retention_pass) is None

    assert "RuntimeError" in caplog.text
    assert "private detail" not in caplog.text
    assert await _exists(old), "nothing of a failed pass is committed"
    assert await _pass_rows() == []


async def test_the_loop_survives_a_failing_pass_and_stops_cleanly(monkeypatch) -> None:
    calls: list[str] = []

    async def fails():
        calls.append("retention")
        raise RuntimeError("boom")

    async def works():
        calls.append("currency")
        return {}

    monkeypatch.setattr(scheduled_passes, "run_retention_pass", fails)
    monkeypatch.setattr(scheduled_passes, "run_currency_pass", works)
    monkeypatch.setattr(scheduled_passes, "STARTUP_DELAY_SECONDS", 0)
    monkeypatch.setattr(scheduled_passes, "WAKE_SECONDS", 0.01)

    await scheduled_passes.start()
    try:
        await asyncio.sleep(0.1)
        task = scheduled_passes._task
        assert task is not None and not task.done(), "the loop is still running after failures"
    finally:
        await scheduled_passes.stop()
    assert task.cancelled()
    assert calls.count("retention") >= 2, "it kept trying"
    assert calls.count("currency") == 1, "the other pass ran, and is itself daily"
    assert scheduled_passes._task is None


async def test_it_never_touches_the_console_categories_which_stay_manual(monkeypatch) -> None:
    """A purge category set by an administrator requires its dry run. This pass ignores it."""
    monkeypatch.setattr(settings, "chat_retention_days", 0)
    chat = await _conversation(age_days=4000)
    async with AsyncSessionLocal() as session:
        await session.execute(delete(RetentionPolicy))
        session.add(RetentionPolicy(category="chat_history", days=7))
        await session.commit()
    try:
        assert await scheduled_passes.run_retention_pass() == {"status": "off"}
        assert await _exists(chat)
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(RetentionPolicy))
            await session.commit()


async def test_the_app_starts_and_stops_the_loop_without_waiting_for_it(monkeypatch) -> None:
    monkeypatch.setattr(scheduled_passes, "STARTUP_DELAY_SECONDS", 3600)
    await scheduled_passes.start()
    first = scheduled_passes._task
    await scheduled_passes.start()
    assert scheduled_passes._task is first, "a second start does not start a second loop"
    await asyncio.wait_for(scheduled_passes.stop(), timeout=2)
