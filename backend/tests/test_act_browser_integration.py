"""The Act routes through the app. The store is faked; sign-in needs PostgreSQL."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.routers import law as law_router
from app.services.act_browser import ActBrowser
from main import app
from tests.helpers import provision_test_user, unique_email

pytestmark = pytest.mark.integration


class _Store:
    def __init__(self) -> None:
        self.calls = 0

    async def scroll(self, **kwargs):
        self.calls += 1
        return [
            SimpleNamespace(id=str(i), payload={"act_name": "Consumer Protection Act, 2019", "section": section})
            for i, section in enumerate(["10", "2", "2A"])
        ], None


async def test_acts_build_once_then_list_their_sections_in_order(monkeypatch) -> None:
    browser = ActBrowser()
    monkeypatch.setattr(law_router, "act_browser", browser)
    store = _Store()
    monkeypatch.setattr(app.state, "retrieval_service", SimpleNamespace(client=store), raising=False)
    account = await provision_test_user(
        name="Act Reader", email=unique_email("acts"), password="Act-browser-Pass-123!", role="citizen"
    )
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get("/law/acts", params={"name": "consumer"}, headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["ready"] is False
        await browser.wait_for_build()

        listed = (await client.get("/law/acts", params={"name": "consumer"}, headers=headers)).json()
        assert listed["ready"] is True
        act = listed["acts"][0]
        assert act["name"] == "Consumer Protection Act, 2019"
        assert act["section_count"] == 3

        sections = await client.get(f"/law/acts/{act['id']}/sections", headers=headers)
        assert sections.status_code == 200, sections.text
        assert [row["section"] for row in sections.json()["sections"]] == ["2", "2A", "10"]
        assert sections.json()["sections"][0]["citation"] == "Section 2 of Consumer Protection Act, 2019"

        missing = await client.get("/law/acts/0000000000000000/sections", headers=headers)
        assert missing.status_code == 404
    assert store.calls == 1


async def test_the_routes_require_sign_in() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/law/acts")).status_code == 401
        assert (await client.get("/law/acts/abc/sections")).status_code == 401
