"""PLAT-07: searching and organising your own conversations."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import AsyncSessionLocal
from app.models import ChatMessage, ChatSession
from app.models.enums import ChatMessageRole
from app.services.history import escape_like, snippet_around
from main import app
from tests.helpers import provision_test_user, unique_email

pytestmark = pytest.mark.integration


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _account() -> dict:
    body = await provision_test_user(
        name="History Holder", email=unique_email("history"), password="History-Password-123", role="citizen"
    )
    return {"id": uuid.UUID(body["user"]["id"]), "token": body["access_token"]}


async def _chat(user_id: uuid.UUID, title: str, *messages: str) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        chat = ChatSession(user_id=user_id, title=title)
        session.add(chat)
        await session.flush()
        for content in messages:
            session.add(ChatMessage(session_id=chat.id, role=ChatMessageRole.USER, content=content, citations=[]))
        await session.commit()
        return chat.id


async def _search(client: AsyncClient, account: dict, term: str, **extra) -> dict:
    response = await client.post(
        "/history/search", json={"term": term, **extra}, headers=_bearer(account["token"])
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_search_finds_titles_and_message_bodies_without_regard_to_case() -> None:
    account = await _account()
    by_title = await _chat(account["id"], "Tenant deposit dispute", "first")
    by_body = await _chat(account["id"], "Something else", "The landlord kept my DEPOSIT after I left")
    await _chat(account["id"], "Unrelated", "nothing to see")
    async with _client() as client:
        found = await _search(client, account, "deposit")
    assert {item["id"] for item in found["items"]} == {str(by_title), str(by_body)}
    snippet = next(item for item in found["items"] if item["id"] == str(by_body))["match_snippet"]
    assert "DEPOSIT" in snippet


async def test_search_never_reaches_another_persons_history() -> None:
    mine, other = await _account(), await _account()
    secret = f"secretword{uuid.uuid4().hex}"
    await _chat(other["id"], secret, secret)
    async with _client() as client:
        assert (await _search(client, mine, secret))["items"] == []


async def test_wildcards_in_a_search_are_literal() -> None:
    account = await _account()
    percent = await _chat(account["id"], "refund", "they promised a 100% refund")
    await _chat(account["id"], "other", "they promised a 100 rupee refund")
    await _chat(account["id"], "another", "no match here at all")
    async with _client() as client:
        literal = await _search(client, account, "100%")
        anything = await _search(client, account, "%")
        underscore = await _search(client, account, "_")
    assert [item["id"] for item in literal["items"]] == [str(percent)]
    assert [item["id"] for item in anything["items"]] == [str(percent)]
    assert underscore["items"] == []


async def test_a_blank_search_is_refused_and_the_term_never_goes_in_a_url() -> None:
    account = await _account()
    async with _client() as client:
        blank = await client.post("/history/search", json={"term": "   "}, headers=_bearer(account["token"]))
        as_get = await client.get("/history/search", headers=_bearer(account["token"]))
    assert blank.status_code == 422
    assert as_get.status_code == 405


async def test_paging_passes_thirty_and_loses_nothing_even_when_timestamps_tie() -> None:
    """Messages in one transaction share a timestamp, so a cursor on time alone skips rows."""
    account = await _account()
    async with AsyncSessionLocal() as session:
        created = []
        for index in range(35):
            chat = ChatSession(user_id=account["id"], title=f"Conversation {index}")
            session.add(chat)
            await session.flush()
            session.add(ChatMessage(session_id=chat.id, role=ChatMessageRole.USER, content="body", citations=[]))
            created.append(str(chat.id))
        await session.commit()

    seen: list[str] = []
    cursor = None
    pages = 0
    async with _client() as client:
        while True:
            params = {"limit": 10, **({"cursor": cursor} if cursor else {})}
            response = await client.get("/history/sessions", params=params, headers=_bearer(account["token"]))
            assert response.status_code == 200, response.text
            body = response.json()
            seen.extend(item["id"] for item in body["items"])
            pages += 1
            cursor = body["next_cursor"]
            if not cursor:
                break
    assert pages == 4
    assert sorted(seen) == sorted(created)
    assert len(set(seen)) == 35


async def test_search_pages_too() -> None:
    account = await _account()
    for index in range(5):
        await _chat(account["id"], f"needle {index}", "needle")
    async with _client() as client:
        first = await _search(client, account, "needle", limit=3)
        second = await _search(client, account, "needle", limit=3, cursor=first["next_cursor"])
    assert len(first["items"]) == 3 and len(second["items"]) == 2
    assert second["next_cursor"] is None
    assert not {item["id"] for item in first["items"]} & {item["id"] for item in second["items"]}


async def test_a_bad_cursor_is_refused() -> None:
    account = await _account()
    async with _client() as client:
        response = await client.get(
            "/history/sessions", params={"cursor": "nonsense"}, headers=_bearer(account["token"])
        )
    assert response.status_code == 422


async def test_a_pin_survives_on_the_server() -> None:
    account = await _account()
    chat = await _chat(account["id"], "Keep this", "body")
    await _chat(account["id"], "Not this", "body")
    headers = _bearer(account["token"])
    async with _client() as client:
        assert (await client.put(f"/history/sessions/{chat}/pin", json={"pinned": True}, headers=headers)).status_code == 204
        pinned = (await client.get("/history/sessions", params={"pinned": True}, headers=headers)).json()
        assert [item["id"] for item in pinned["items"]] == [str(chat)]
        assert pinned["items"][0]["pinned"] is True
        await client.put(f"/history/sessions/{chat}/pin", json={"pinned": False}, headers=headers)
        assert (await client.get("/history/sessions", params={"pinned": True}, headers=headers)).json()["items"] == []


async def test_pins_are_capped_and_re_pinning_does_not_count_twice() -> None:
    account = await _account()
    headers = _bearer(account["token"])
    chats = [await _chat(account["id"], f"Chat {index}", "body") for index in range(6)]
    async with _client() as client:
        for chat in chats[:5]:
            assert (await client.put(f"/history/sessions/{chat}/pin", json={"pinned": True}, headers=headers)).status_code == 204
        assert (await client.put(f"/history/sessions/{chats[0]}/pin", json={"pinned": True}, headers=headers)).status_code == 204
        over = await client.put(f"/history/sessions/{chats[5]}/pin", json={"pinned": True}, headers=headers)
    assert over.status_code == 409


async def test_a_matter_organises_and_filters() -> None:
    account = await _account()
    headers = _bearer(account["token"])
    first = await _chat(account["id"], "One", "body")
    second = await _chat(account["id"], "Two", "body")
    await _chat(account["id"], "Three", "body")
    async with _client() as client:
        for chat in (first, second):
            response = await client.put(
                f"/history/sessions/{chat}/matter", json={"matter": "  Rent   dispute "}, headers=headers
            )
            assert response.status_code == 204
        filtered = (await client.get("/history/sessions", params={"matter": "Rent dispute"}, headers=headers)).json()
        assert {item["id"] for item in filtered["items"]} == {str(first), str(second)}
        matters = (await client.get("/history/matters", headers=headers)).json()["items"]
        assert matters == [{"matter": "Rent dispute", "count": 2}]
        await client.put(f"/history/sessions/{first}/matter", json={"matter": None}, headers=headers)
        again = (await client.get("/history/matters", headers=headers)).json()["items"]
        assert again == [{"matter": "Rent dispute", "count": 1}]


async def test_pin_and_matter_are_also_found_when_searching_by_matter_name() -> None:
    account = await _account()
    headers = _bearer(account["token"])
    chat = await _chat(account["id"], "Plain title", "plain body")
    async with _client() as client:
        await client.put(f"/history/sessions/{chat}/matter", json={"matter": "Boundary wall"}, headers=headers)
        found = await _search(client, account, "boundary")
    assert [item["id"] for item in found["items"]] == [str(chat)]


async def test_nobody_can_organise_someone_elses_conversation() -> None:
    owner, stranger, admin_body = await _account(), await _account(), await provision_test_user(
        name="Admin", email=unique_email("history-admin"), password="History-Password-123", role="admin"
    )
    chat = await _chat(owner["id"], "Mine", "body")
    async with _client() as client:
        for headers in (_bearer(stranger["token"]), _bearer(admin_body["access_token"])):
            pin = await client.put(f"/history/sessions/{chat}/pin", json={"pinned": True}, headers=headers)
            matter = await client.put(f"/history/sessions/{chat}/matter", json={"matter": "x"}, headers=headers)
            assert (pin.status_code, matter.status_code) == (404, 404)
        missing = await client.put(
            f"/history/sessions/{uuid.uuid4()}/pin", json={"pinned": True}, headers=_bearer(stranger["token"])
        )
        assert missing.status_code == 404
        pinned = (await client.get("/history/sessions", params={"pinned": True}, headers=_bearer(owner["token"]))).json()
    assert pinned["items"] == []


async def test_deleting_a_conversation_removes_its_organisation_too() -> None:
    account = await _account()
    headers = _bearer(account["token"])
    chat = await _chat(account["id"], "Going", "body")
    async with _client() as client:
        await client.put(f"/history/sessions/{chat}/pin", json={"pinned": True}, headers=headers)
        assert (await client.delete(f"/chat/sessions/{chat}", headers=headers)).status_code == 204
        pinned = (await client.get("/history/sessions", params={"pinned": True}, headers=headers)).json()
    assert pinned["items"] == []


def test_escape_like() -> None:
    assert escape_like(r"50%_\x") == r"50\%\_\\x"


def test_snippet_is_a_window_around_the_match() -> None:
    long_text = "a " * 200 + "needle" + " b" * 200
    snippet = snippet_around(long_text, "NEEDLE")
    assert "needle" in snippet
    assert snippet.startswith("…") and snippet.endswith("…")
    assert len(snippet) < 170
