"""A citation opens that provision or says it is not held. It never guesses."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.law_lookup import CONSTITUTION, lookup_provision, parse_citation


@pytest.mark.parametrize(
    "text, act, section, code",
    [
        ("IPC 420", "Indian Penal Code", "420", "IPC"),
        ("ipc 420", "Indian Penal Code", "420", "IPC"),
        ("420 IPC", None, None, None),
        ("Section 103 BNS", "Bharatiya Nyaya Sanhita", "103", "BNS"),
        ("s. 35(3) of the BNSS", "Bharatiya Nagarik Suraksha Sanhita", "35(3)", "BNSS"),
        ("Sec 154 CrPC", "Code of Criminal Procedure", "154", "CrPC"),
        ("BNSS section 173", "Bharatiya Nagarik Suraksha Sanhita", "173", "BNSS"),
        ("Article 21", CONSTITUTION, "21", None),
        ("IT Act 66C", "Information Technology Act", "66C", None),
        ("POCSO 19", "Protection of Children from Sexual Offences Act", "19", None),
        ("Consumer Protection Act, 2019 section 35", "Consumer Protection Act, 2019", "35", None),
    ],
)
def test_the_forms_people_type(text, act, section, code) -> None:
    citation = parse_citation(text)
    if act is None:
        assert citation is None
        return
    assert citation.act == act
    assert citation.section == section
    assert citation.code == code


@pytest.mark.parametrize(
    "text",
    ["", "What is the punishment for theft?", "Consumer Protection Act 2019", "bail", "x" * 200],
)
def test_a_question_or_a_bare_act_name_is_not_a_citation(text) -> None:
    assert parse_citation(text) is None


class _Client:
    def __init__(self, *payloads: dict) -> None:
        self.points = [SimpleNamespace(id=str(i), payload=p) for i, p in enumerate(payloads)]
        self.scrolls = []

    async def scroll(self, **kwargs):
        self.scrolls.append(kwargs)
        return self.points, None

    async def retrieve(self, *, ids, **kwargs):
        return [point for point in self.points if point.id in ids]


def _payload(**overrides) -> dict:
    return {
        "chunk_id": "a",
        "canonical_document_id": "doc-1",
        "title": "Bharatiya Nyaya Sanhita, 2023",
        "act_name": "Bharatiya Nyaya Sanhita, 2023",
        "section": "103",
        "text": "Punishment for murder.",
        "page_start": 30,
        "page_end": 30,
        "document_type": "bare_act",
        "verified_official": "True",
        **overrides,
    }


async def test_a_section_split_over_chunks_reads_in_page_order() -> None:
    client = _Client(
        _payload(chunk_id="b", text="Second part.", page_start=31, page_end=31),
        _payload(chunk_id="a", text="First part."),
    )
    result = await lookup_provision(client, "BNS 103", collection="c")
    provision = result["provisions"][0]
    assert provision["text"] == "First part.\n\nSecond part."
    assert (provision["page_start"], provision["page_end"]) == (30, 31)


async def test_nothing_held_is_an_empty_list_not_a_neighbour() -> None:
    result = await lookup_provision(_Client(), "BNS 9999", collection="c")
    assert result["understood"] is True
    assert result["provisions"] == []


async def test_the_filter_is_exact_on_the_section_and_uses_the_base_of_a_subsection() -> None:
    client = _Client()
    await lookup_provision(client, "s.35(3) BNSS", collection="c")
    conditions = client.scrolls[0]["scroll_filter"].must
    assert len(conditions) == 1
    assert conditions[0].key == "section"
    assert conditions[0].match.value == "35"


async def test_a_question_does_not_reach_the_corpus() -> None:
    client = _Client()
    result = await lookup_provision(client, "what is theft", collection="c")
    assert result["understood"] is False
    assert client.scrolls == []


async def test_a_quarantined_document_is_not_shown(monkeypatch) -> None:
    monkeypatch.setattr("app.services.law_lookup.is_quarantined", lambda document: document == "doc-1")
    result = await lookup_provision(_Client(_payload()), "BNS 103", collection="c")
    assert result["provisions"] == []


async def test_the_bare_act_outranks_a_longer_commentary() -> None:
    client = _Client(
        _payload(canonical_document_id="doc-2", document_type="report", text="long " * 500),
        _payload(),
    )
    result = await lookup_provision(client, "BNS 103", collection="c")
    assert result["provisions"][0]["text"] == "Punishment for murder."


async def test_the_act_is_matched_whatever_its_title_case() -> None:
    client = _Client(_payload(act_name="THE BHARATIYA NYAYA SANHITA, 2023"))
    assert (await lookup_provision(client, "BNS 103", collection="c"))["provisions"]


async def test_the_same_number_in_another_act_is_not_shown() -> None:
    client = _Client(_payload(act_name="The Companies Act, 2013"))
    assert (await lookup_provision(client, "BNS 103", collection="c"))["provisions"] == []


async def test_a_year_in_the_citation_picks_that_act() -> None:
    client = _Client(_payload(act_name="Consumer Protection Act, 1986"))
    assert (await lookup_provision(client, "Consumer Protection Act 2019 s.35", collection="c"))["provisions"] == []


async def test_the_act_itself_outranks_a_circular_naming_it() -> None:
    client = _Client(
        _payload(canonical_document_id="doc-2", act_name="Implementation of the Bharatiya Nyaya Sanhita in prisons", text="long " * 500),
        _payload(),
    )
    assert (await lookup_provision(client, "BNS 103", collection="c"))["provisions"][0]["text"] == "Punishment for murder."


async def test_counterparts_are_one_row_per_target_and_drop_garbled_entries(monkeypatch) -> None:
    from app.services.section_mapping import SectionMapping

    def row(to_section, subject="", changed=False):
        return SectionMapping("CrPC", "154", "BNSS", to_section, subject, changed)

    monkeypatch.setattr(
        "app.services.law_lookup.map_sections",
        lambda code, section: (row("173"), row("173", "Information", True), row(", 35(4)"), row(None)),
    )
    result = await lookup_provision(_Client(), "CrPC 154", collection="c")
    assert [(c["to_section"], c["subject"], c["ingredients_changed"]) for c in result["counterparts"]] == [
        ("173", "Information", True),
        (None, "", False),
    ]
