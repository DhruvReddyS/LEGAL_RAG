"""CORP-06: a saved answer's law changes, and only its owner is told.

The titles and statuses below are invented for the test. A temporary currency table
and manifest drive the real resolution, so no statement about real law is made here.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import AuditLog, ChatMessage, ChatSession
from app.models.corpus_lifecycle import DocumentCurrencyState, LawChangeNotice
from app.models.enums import ChatMessageRole
from app.services import currency, law_changes
from app.services.currency import CurrencyDecision, CurrencyStatus
from main import app
from tests.helpers import provision_test_user, unique_email

pytestmark = pytest.mark.integration

PASSWORD = "Original-Password-1234"
SECRET_QUESTION = "my landlord Vikram threatened me on Tuesday"
SECRET_ANSWER = "An answer that repeats the private detail about Vikram."


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class World:
    """A temp manifest and currency table the test can change between passes."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.title = f"The Invented Act {uuid.uuid4().hex[:8]}, 2001"
        self.canonical_id = f"test-canonical-{uuid.uuid4().hex[:24]}"
        (root / "metadata").mkdir(parents=True)
        checksum = hashlib.sha256(self.canonical_id.encode()).hexdigest()
        row = {
            "act_name": self.title,
            "canonical_document_id": self.canonical_id,
            "category": "primary_law/test",
            "current_status": "current/verify",
            "document_id": f"test-doc-{self.canonical_id}",
            "file_size": 1,
            "local_path": "raw/x.pdf",
            "original_filename": "x.pdf",
            "page_count": 1,
            "quality_status": "verified",
            "sha256": checksum,
            "source_id": "x",
            "source_type": "act",
            "title": self.title,
            "verified_official": True,
        }
        (root / "metadata/canonical_documents.jsonl").write_text(json.dumps(row) + "\n")
        self.set_entries([])

    def set_entries(self, entries: list[dict]) -> None:
        (self.root / "metadata/currency_status.json").write_text(json.dumps({"entries": entries}))

    def supersede(self, successor: str = "The Invented Successor Act, 2030") -> None:
        self.set_entries(
            [
                {
                    "starts_with": self.title.casefold(),
                    "status": "superseded",
                    "superseded_by": successor,
                    "effective": "2030-01-01",
                    "basis": "Invented for this test.",
                }
            ]
        )


@pytest_asyncio.fixture(loop_scope="session")
async def world(tmp_path, monkeypatch):
    built = World(tmp_path)
    monkeypatch.setattr(settings, "legal_kb_root", str(tmp_path))
    monkeypatch.setattr(currency, "_DEFAULT_TABLE", tmp_path / "metadata/currency_status.json")
    currency._entries.cache_clear()
    async with AsyncSessionLocal() as session:
        await session.execute(delete(DocumentCurrencyState))
        await session.commit()
    yield built
    monkeypatch.undo()
    currency._entries.cache_clear()
    async with AsyncSessionLocal() as session:
        await session.execute(delete(DocumentCurrencyState))
        await session.commit()


async def _account(role: str = "citizen") -> dict:
    body = await provision_test_user(
        name="Asha Rao", email=unique_email(f"notice-{role}"), password=PASSWORD, role=role
    )
    return {"id": uuid.UUID(body["user"]["id"]), "token": body["access_token"]}


async def _saved_answer(user_id: uuid.UUID, citations: list[dict], *, session_title: str = "My question") -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        chat = ChatSession(user_id=user_id, title=session_title)
        session.add(chat)
        await session.flush()
        session.add(ChatMessage(session_id=chat.id, role=ChatMessageRole.USER, content=SECRET_QUESTION, citations=[]))
        answer = ChatMessage(
            session_id=chat.id, role=ChatMessageRole.ASSISTANT, content=SECRET_ANSWER, citations=citations
        )
        session.add(answer)
        await session.commit()
        return answer.id


def _citation(title: str, **extra) -> dict:
    return {
        "number": 1,
        "chunk_id": "gold-chunk-abc",
        "title": title,
        "act_name": title,
        "current_status": "status_unverified",
        "excerpt": "Some provision.",
        **extra,
    }


async def _sync() -> dict:
    async with AsyncSessionLocal() as session:
        return await law_changes.sync_currency_notices(session)


async def _notices(token: str) -> dict:
    async with _client() as client:
        response = await client.get("/account/law-changes", headers=_bearer(token))
    assert response.status_code == 200
    return response.json()


# ------------------------------------------------------------------- the change


async def test_the_first_pass_records_without_telling_anyone(world) -> None:
    world.supersede()
    account = await _account()
    await _saved_answer(account["id"], [_citation(world.title)])

    outcome = await _sync()

    assert outcome["status"] == "baseline" and outcome["notices_written"] == 0
    assert (await _notices(account["token"]))["unread"] == 0


async def test_a_change_notifies_the_owner_with_the_curated_facts(world) -> None:
    account = await _account()
    await _saved_answer(account["id"], [_citation(world.title)], session_title="Landlord trouble")
    await _sync()

    world.supersede("The Invented Successor Act, 2030")
    outcome = await _sync()

    assert outcome["changes_to_notify"] == 1 and outcome["notices_written"] == 1
    body = await _notices(account["token"])
    assert body["unread"] == 1
    notice = body["notices"][0]
    assert notice["document_title"] == world.title
    assert notice["previous_status"] == "unverified" and notice["current_status"] == "superseded"
    assert notice["superseded_by"] == "The Invented Successor Act, 2030"
    assert notice["effective"] == "2030-01-01"
    assert notice["basis"] == "Invented for this test."
    assert notice["conversation_title"] == "Landlord trouble"


async def test_a_pass_with_no_change_writes_nothing_twice(world) -> None:
    account = await _account()
    await _saved_answer(account["id"], [_citation(world.title)])
    await _sync()
    world.supersede()
    assert (await _sync())["notices_written"] == 1
    assert (await _sync())["notices_written"] == 0
    assert (await _notices(account["token"]))["unread"] == 1


async def test_an_answer_that_already_said_so_is_not_notified(world) -> None:
    told = await _account()
    await _saved_answer(
        told["id"],
        [_citation(world.title, current_status="repealed", replaced_by="The Invented Successor Act, 2030")],
    )
    await _sync()
    world.supersede("The Invented Successor Act, 2030")
    assert (await _sync())["notices_written"] == 0


async def test_a_new_successor_reaches_an_answer_that_named_the_old_one(world) -> None:
    told = await _account()
    await _saved_answer(told["id"], [_citation(world.title, current_status="repealed", replaced_by="First Successor")])
    world.supersede("First Successor")
    await _sync()
    world.supersede("Second Successor")
    assert (await _sync())["notices_written"] == 1
    assert (await _notices(told["token"]))["notices"][0]["superseded_by"] == "Second Successor"


async def test_a_correction_tells_only_those_told_it_was_repealed(world) -> None:
    told_repealed, told_nothing = await _account(), await _account()
    await _saved_answer(told_repealed["id"], [_citation(world.title, current_status="repealed")])
    await _saved_answer(told_nothing["id"], [_citation(world.title)])
    world.supersede()
    await _sync()
    world.set_entries([{"starts_with": world.title.casefold(), "status": "in_force", "basis": "Invented."}])

    assert (await _sync())["notices_written"] == 1
    assert (await _notices(told_repealed["token"]))["unread"] == 1
    assert (await _notices(told_nothing["token"]))["unread"] == 0


def _decision(status: CurrencyStatus, successor: str | None = None) -> CurrencyDecision:
    return CurrencyDecision(status=status, superseded_by=successor)


@pytest.mark.parametrize(
    "previous,successor,decision,expected",
    [
        ("unverified", None, _decision(CurrencyStatus.IN_FORCE), False),
        ("in_force", None, _decision(CurrencyStatus.UNVERIFIED), False),
        ("unverified", None, _decision(CurrencyStatus.SUPERSEDED, "B"), True),
        ("in_force", None, _decision(CurrencyStatus.SUPERSEDED, "B"), True),
        ("superseded", "B", _decision(CurrencyStatus.IN_FORCE), True),
        ("superseded", "B", _decision(CurrencyStatus.SUPERSEDED, "B"), False),
        ("superseded", "B", _decision(CurrencyStatus.SUPERSEDED, "C"), True),
    ],
)
def test_which_changes_are_worth_telling_someone(previous, successor, decision, expected) -> None:
    assert law_changes.is_worth_telling_someone(previous, successor, decision) is expected


async def test_a_missing_manifest_is_not_every_act_being_repealed(world, monkeypatch, tmp_path) -> None:
    account = await _account()
    await _saved_answer(account["id"], [_citation(world.title)])
    await _sync()
    monkeypatch.setattr(settings, "legal_kb_root", str(tmp_path / "unmounted"))
    outcome = await _sync()
    assert outcome["status"] == "skipped"
    monkeypatch.setattr(settings, "legal_kb_root", str(world.root))
    assert await _count_states() == 1


async def _count_states() -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(select(func.count()).select_from(DocumentCurrencyState)))


async def test_a_second_instance_stands_aside(world) -> None:
    await _sync()
    async with AsyncSessionLocal() as holder:
        assert await holder.scalar(select(func.pg_try_advisory_xact_lock(law_changes.SYNC_LOCK_KEY)))
        outcome = await _sync()
        await holder.rollback()
    assert outcome["status"] == "skipped"


# ----------------------------------------------------------------- the boundary


async def test_nobody_else_sees_or_can_touch_a_notice(world) -> None:
    owner, stranger = await _account(), await _account()
    await _saved_answer(owner["id"], [_citation(world.title)], session_title="Private matter title")
    await _saved_answer(stranger["id"], [_citation("Some other Act")])
    await _sync()
    world.supersede()
    await _sync()

    assert (await _notices(stranger["token"])) == {"unread": 0, "notices": []}
    notice_id = (await _notices(owner["token"]))["notices"][0]["id"]
    async with _client() as client:
        refused = await client.post(f"/account/law-changes/{notice_id}/read", headers=_bearer(stranger["token"]))
        await client.post("/account/law-changes/read-all", headers=_bearer(stranger["token"]))
        anonymous = await client.get("/account/law-changes")
    assert refused.status_code == 404
    assert anonymous.status_code == 401
    assert (await _notices(owner["token"]))["unread"] == 1, "a stranger's read-all reached nothing of mine"


async def test_a_notice_carries_nothing_of_the_conversation(world) -> None:
    account = await _account()
    await _saved_answer(account["id"], [_citation(world.title)])
    await _sync()
    world.supersede()
    await _sync()
    body = json.dumps(await _notices(account["token"]))
    assert "Vikram" not in body and "private detail" not in body
    async with AsyncSessionLocal() as session:
        rows = (await session.scalars(select(AuditLog).where(AuditLog.action == "corpus.currency_sync"))).all()
    assert all("Vikram" not in json.dumps(row.metadata_) for row in rows)


async def test_case_evidence_citations_never_raise_a_notice(world) -> None:
    account = await _account()
    await _saved_answer(account["id"], [_citation(world.title, chunk_id="case-chunk-private")])
    await _sync()
    world.supersede()
    assert (await _sync())["notices_written"] == 0


async def test_reading_clears_the_count_and_keeps_the_notice(world) -> None:
    account = await _account()
    await _saved_answer(account["id"], [_citation(world.title)])
    await _saved_answer(account["id"], [_citation(world.title)])
    await _sync()
    world.supersede()
    await _sync()
    body = await _notices(account["token"])
    assert body["unread"] == 2
    async with _client() as client:
        one = await client.post(f"/account/law-changes/{body['notices'][0]['id']}/read", headers=_bearer(account["token"]))
        assert one.status_code == 204
        assert (await _notices(account["token"]))["unread"] == 1
        everything = await client.post("/account/law-changes/read-all", headers=_bearer(account["token"]))
    assert everything.json() == {"marked_read": 1}
    after = await _notices(account["token"])
    assert after["unread"] == 0 and len(after["notices"]) == 2


async def test_deleting_the_conversation_takes_its_notice_with_it(world) -> None:
    account = await _account()
    message_id = await _saved_answer(account["id"], [_citation(world.title)])
    await _sync()
    world.supersede()
    await _sync()
    async with AsyncSessionLocal() as session:
        message = await session.get(ChatMessage, message_id)
        await session.execute(delete(ChatSession).where(ChatSession.id == message.session_id))
        await session.commit()
        remaining = await session.scalar(
            select(func.count()).select_from(LawChangeNotice).where(LawChangeNotice.user_id == account["id"])
        )
    assert remaining == 0


async def test_an_administrator_can_run_the_pass_and_a_citizen_cannot(world) -> None:
    admin, citizen = await _account("admin"), await _account()
    async with _client() as client:
        refused = await client.post("/admin/console/corpus/currency-notices/sync", headers=_bearer(citizen["token"]))
        allowed = await client.post("/admin/console/corpus/currency-notices/sync", headers=_bearer(admin["token"]))
    assert refused.status_code == 403
    assert allowed.status_code == 200 and allowed.json()["status"] == "baseline"


async def test_notices_are_part_of_a_persons_export(world) -> None:
    from app.models import User
    from app.services.privacy import build_export

    account = await _account()
    await _saved_answer(account["id"], [_citation(world.title)])
    await _sync()
    world.supersede()
    await _sync()
    async with AsyncSessionLocal() as session:
        user = await session.get(User, account["id"])
        export = await build_export(session, user)
    assert [row["document_title"] for row in export["law_change_notices"]] == [world.title]
