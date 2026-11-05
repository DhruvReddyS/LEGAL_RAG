"""Browsing an Act: one background build, then memory. Requests never scroll."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import act_browser as browser_module
from app.services.act_browser import (
    INDEX_TTL_SECONDS,
    RETRY_AFTER_SECONDS,
    ActBrowser,
    build_index,
    citation_for,
    clean_section,
    search_acts,
    section_sort_key,
)
from app.services.law_lookup import parse_citation


def _point(act: str, section: str, document: str = "doc") -> SimpleNamespace:
    return SimpleNamespace(id=f"{act}-{section}", payload={"act_name": act, "section": section, "canonical_document_id": document})


class _Client:
    def __init__(self, *points, page: int = 2, fail: bool = False) -> None:
        self.points = list(points)
        self.page = page
        self.fail = fail
        self.calls: list[dict] = []

    async def scroll(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise ConnectionError("store down")
        start = kwargs.get("offset") or 0
        end = start + self.page
        return self.points[start:end], (end if end < len(self.points) else None)


def test_sections_sort_by_number_then_letter() -> None:
    sections = ["10", "2", "120B", "120", "1", "120A", "100"]
    assert sorted(sections, key=section_sort_key) == ["1", "2", "10", "100", "120", "120A", "120B"]


@pytest.mark.parametrize(
    "raw, expected",
    [("35(3)", "35"), ("21a", "21A"), (" 7 ", "7"), ("", None), (None, None), ("Schedule", None), ("12345", None), ("IV", None)],
)
def test_only_section_numbers_are_listed(raw, expected) -> None:
    assert clean_section(raw) == expected


def test_one_act_however_its_chunks_repeat_or_are_capitalised() -> None:
    index = build_index(
        [
            ("Consumer Protection Act, 2019", "35"),
            ("Consumer Protection Act, 2019", "35"),
            ("Consumer Protection Act, 2019", "2"),
            ("THE CONSUMER PROTECTION ACT, 2019", "100"),
            ("", "4"),
            ("Consumer Protection Act, 2019", "not a number"),
        ]
    )
    assert len(index.acts) == 1
    act = index.acts[0]
    assert act.name == "Consumer Protection Act, 2019"
    assert act.sections == ("2", "35", "100")
    assert index.by_id[act.id] is act


def test_an_act_keeps_its_id_across_builds() -> None:
    one = build_index([("Evidence Act, 1872", "1")]).acts[0].id
    two = build_index([("The Evidence Act, 1872", "2"), ("Other Act, 2000", "1")]).by_id[one]
    assert two.sections == ("2",)


def _index():
    return build_index(
        [
            ("Indian Penal Code, 1860", "420"),
            ("Consumer Protection Act, 2019", "35"),
            ("Consumer Protection Act, 1986", "12"),
            ("The Protection of Women from Domestic Violence Act, 2005", "12"),
            ("Constitution of India", "21"),
            ("Bharatiya Nyaya Sanhita, 2023", "103"),
        ]
    )


@pytest.mark.parametrize(
    "name, first",
    [
        ("consumer", "Consumer Protection Act, 1986"),
        ("CONSUMER PROT", "Consumer Protection Act, 1986"),
        ("protection 2019", "Consumer Protection Act, 2019"),
        ("constitution", "Constitution of India"),
        ("IPC", "Indian Penal Code, 1860"),
        ("bns", "Bharatiya Nyaya Sanhita, 2023"),
        ("dv act", "The Protection of Women from Domestic Violence Act, 2005"),
    ],
)
def test_search_is_case_blind_prefix_matching_with_shorthand(name, first) -> None:
    found, _ = search_acts(_index(), name)
    assert found[0].name == first


def test_search_finds_nothing_rather_than_something_near() -> None:
    assert search_acts(_index(), "motor vehicles") == ([], 0)


def test_an_empty_search_lists_acts_up_to_the_limit() -> None:
    found, total = search_acts(_index(), "   ", limit=2)
    assert (len(found), total) == (2, 6)


@pytest.mark.parametrize(
    "act, section, parsed_act, parsed_section",
    [
        ("Indian Penal Code, 1860", "420", "Indian Penal Code", "420"),
        ("Bharatiya Nagarik Suraksha Sanhita, 2023", "173", "Bharatiya Nagarik Suraksha Sanhita", "173"),
        ("Consumer Protection Act, 2019", "35", "Consumer Protection Act, 2019", "35"),
        ("Constitution of India", "21A", "Constitution of India", "21A"),
    ],
)
def test_a_listed_section_reads_back_through_the_lookup(act, section, parsed_act, parsed_section) -> None:
    citation = citation_for(act, section)
    parsed = parse_citation(citation)
    assert parsed.act == parsed_act
    assert parsed.section == parsed_section


def test_the_constitution_is_cited_by_article() -> None:
    assert citation_for("The Constitution of India", "21") == "Article 21 of The Constitution of India"
    assert citation_for("Consumer Protection Act, 2019", "2").startswith("Section 2 of")


def test_a_very_long_name_still_gives_a_citation_the_lookup_accepts() -> None:
    long_name = "The " + " ".join(f"Word{i}" for i in range(40)) + " Act, 1999"
    citation = citation_for(long_name, "5")
    assert citation is not None
    assert len(citation) <= 160
    assert parse_citation(citation).section == "5"


async def test_requests_do_not_scroll_and_the_build_filters_to_bare_acts() -> None:
    client = _Client(_point("A Act, 2000", "1"), _point("A Act, 2000", "2"), _point("B Act, 2001", "1"))
    browser = ActBrowser()
    assert browser.current(client, collection="c") is None
    assert browser.current(client, collection="c") is None, "a second request must not start a second build"
    await browser.wait_for_build()
    assert len(client.calls) == 2, "two pages"
    condition = client.calls[0]["scroll_filter"].must[0]
    assert (condition.key, condition.match.value) == ("document_type", "bare_act")
    assert client.calls[0]["with_vectors"] is False
    assert "text" not in client.calls[0]["with_payload"]

    pages_read = len(client.calls)
    for _ in range(100):
        index = browser.current(client, collection="c")
    await browser.wait_for_build()
    assert len(index.acts) == 2
    assert len(client.calls) == pages_read


async def test_an_old_index_keeps_serving_while_a_new_one_is_built() -> None:
    now = [1000.0]
    client = _Client(_point("A Act, 2000", "1"))
    browser = ActBrowser(clock=lambda: now[0])
    browser.current(client, collection="c")
    await browser.wait_for_build()

    client.points.append(_point("B Act, 2001", "1"))
    now[0] += INDEX_TTL_SECONDS + 1
    served = browser.current(client, collection="c")
    assert [act.name for act in served.acts] == ["A Act, 2000"]
    await browser.wait_for_build()
    assert len(browser.current(client, collection="c").acts) == 2


async def test_a_failed_build_waits_before_trying_again_and_keeps_what_it_had() -> None:
    now = [1000.0]
    client = _Client(fail=True)
    browser = ActBrowser(clock=lambda: now[0])
    browser.current(client, collection="c")
    await browser.wait_for_build()
    assert browser.failing is True
    calls = len(client.calls)
    assert browser.current(client, collection="c") is None
    await browser.wait_for_build()
    assert len(client.calls) == calls, "within the backoff nothing is retried"

    client.fail = False
    client.points.append(_point("A Act, 2000", "1"))
    now[0] += RETRY_AFTER_SECONDS + 1
    browser.current(client, collection="c")
    await browser.wait_for_build()
    assert browser.failing is False
    assert len(browser.current(client, collection="c").acts) == 1


async def test_a_quarantined_document_is_not_listed(monkeypatch) -> None:
    monkeypatch.setattr(browser_module, "is_quarantined", lambda document: document == "bad")
    client = _Client(_point("A Act, 2000", "1", "good"), _point("Noise Act, 2000", "1", "bad"))
    browser = ActBrowser()
    browser.current(client, collection="c")
    await browser.wait_for_build()
    assert [act.name for act in browser.current(client, collection="c").acts] == ["A Act, 2000"]
