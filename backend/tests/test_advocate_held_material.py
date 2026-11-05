"""A-06, A-07, A-08 over a small judgment set, which must never imply completeness."""

from __future__ import annotations

from app.services.judgment_index import JUDGMENT_SOURCE_TYPES

import pytest

from app.services.held_material import check_opponent_authorities, check_treatment, search_precedents
from app.services.judgment_index import (
    CorpusUnavailable,
    JudgmentIndex,
    coverage_of,
    coverage_statement,
    match_parties,
    parse_case_references,
    split_title,
)
from tests.advocate_fakes import FakeQdrant, FakeRetrieval, judgment_chunk

AJITH = "THE STATE OF KERALA vs K.AJITH Crl.A. No. 697/2021"
ARNESH = "ARNESH KUMAR vs STATE OF BIHAR Crl.A. No. 1277/2014"
RAVI = "RAVI SHANKAR vs UNION OF INDIA W.P.(C) No. 12/2024"


def corpus() -> list:
    return [
        judgment_chunk(
            "kerala", AJITH, 1,
            "This is an appeal by the State. The withdrawal of prosecution was refused. "
            "We hold that the public prosecutor must apply an independent mind.",
            year=2021, cited_provisions=("crpc:321",),
        ),
        judgment_chunk(
            "arnesh", ARNESH, 1,
            "Arrest should not be mechanical. We are of the opinion that a magistrate must record satisfaction.",
            year=2014, cited_cases=("2014 INSC 463",), cited_provisions=("crpc:41",),
        ),
        judgment_chunk(
            "ravi", RAVI, 1,
            "Bail was considered in light of Arnesh Kumar v. State of Bihar, which was followed here. "
            "A different line in an unrelated matter was overruled long ago.",
            year=2024, court="High Court of Andhra Pradesh", cited_cases=("Arnesh Kumar v. State",),
        ),
        judgment_chunk(
            "undated", "OLD PARTY vs ANOTHER PARTY", 1, "Bail conditions were discussed at length.", year=None,
        ),
        # Noise held back from retrieval is not searched, so it is not counted.
        judgment_chunk("noise", "NOISE vs NOISE", 1, "Bail noise.", tier="quarantine"),
    ]


def index(records=None) -> JudgmentIndex:
    return JudgmentIndex(FakeQdrant(records if records is not None else corpus()), "c", ttl_seconds=0)


class TestTheCountIsReadNotRemembered:
    async def test_the_count_comes_from_the_index(self):
        coverage = await index().coverage()
        assert coverage.judgments_held == 4
        assert coverage.by_court == {"Supreme Court of India": 3, "High Court of Andhra Pradesh": 1}

    async def test_it_follows_the_corpus_when_the_corpus_grows(self):
        records = corpus()
        idx = index(records)
        assert (await idx.coverage()).judgments_held == 4
        records.append(judgment_chunk("new", "A vs B", 1, "A new judgment.", year=2026))
        assert (await idx.coverage()).judgments_held == 5

    async def test_several_chunks_are_one_judgment(self):
        records = corpus() + [judgment_chunk("kerala", AJITH, 2, "More of the same judgment.", year=2021)]
        assert (await index(records).coverage()).judgments_held == 4

    async def test_an_unreadable_index_gives_an_unknown_not_a_number(self):
        client = FakeQdrant(corpus())
        client.fail = True
        idx = JudgmentIndex(client, "c", ttl_seconds=0)
        assert await idx.coverage() is None
        statement = coverage_statement(None)
        assert statement["judgments_held"] is None
        assert "could not be read" in statement["statement"]
        assert "not evidence that none exists" in statement["absence_note"]


class TestPrecedentSearch:
    async def search(self, **kwargs):
        records = corpus()
        retrieval = FakeRetrieval(records)
        result = await search_precedents(retrieval=retrieval, index=index(records), **kwargs)
        return result, retrieval

    async def test_every_result_states_the_count_and_the_limit(self):
        result, _ = await self.search(query="bail conditions magistrate")
        assert result["coverage"]["judgments_searched"] == 4
        assert "4 judgments" in result["coverage"]["statement"]
        assert result["coverage"]["absence_note"] == "A judgment not found here is not evidence that none exists."

    async def test_a_court_filter_narrows_the_stated_scope(self):
        result, retrieval = await self.search(query="bail", court="High Court of Andhra Pradesh")
        assert result["coverage"]["judgments_searched"] == 1
        assert retrieval.calls[0]["filters"].courts == ["High Court of Andhra Pradesh"]
        assert {row["title"] for row in result["results"]} == {RAVI}

    async def test_a_year_filter_says_it_excludes_undated_judgments(self):
        result, retrieval = await self.search(query="bail", year_from=2020, year_to=2024)
        assert result["coverage"]["judgments_searched"] == 2
        assert "no decision year recorded" in result["scope_note"]
        assert retrieval.calls[0]["filters"].year_from == 2020

    async def test_only_judgments_are_searched(self):
        _, retrieval = await self.search(query="bail")
        assert retrieval.calls[0]["filters"].source_types == list(JUDGMENT_SOURCE_TYPES)

    async def test_nothing_found_is_not_reported_as_nothing_existing(self):
        result, _ = await self.search(query="bail", year_from=1900, year_to=1901)
        assert result["results"] == []
        assert "says nothing about whether such a judgment exists" in result["empty_note"]

    async def test_passages_are_verbatim_and_holding_language_is_labelled_as_wording(self):
        result, _ = await self.search(query="magistrate satisfaction arrest", court="Supreme Court of India")
        arnesh = next(row for row in result["results"] if row["title"] == ARNESH)
        passage = arnesh["passages"][0]
        assert "Arrest should not be mechanical" in passage["source"]["excerpt"]
        assert passage["holding_language"][0].startswith("We are of the opinion")
        assert "not a statement of the ratio" in result["method"]


class TestTreatment:
    async def check(self, reference: str, records=None):
        return await check_treatment(index=index(records), reference_text=reference)

    async def test_it_labels_itself_and_never_says_the_words(self):
        result = await self.check("Arnesh Kumar v. State of Bihar")
        assert result["label"] == "Partial check of held material. This is not a citator."
        assert "good law" not in str({k: v for k, v in result.items() if k != "cited_by"}).casefold()

    async def test_there_is_no_conclusion_field_to_render(self):
        result = await self.check("Arnesh Kumar v. State of Bihar")
        assert not {"status", "verdict", "still_valid", "good_law", "overruled", "conclusion"} & set(result)

    async def test_a_clipped_edge_still_finds_the_citing_judgment(self):
        """Ingestion stored 'Arnesh Kumar v. State', clipped at 'of'."""
        result = await self.check("Arnesh Kumar v. State of Bihar")
        assert [row["title"] for row in result["held"]] == [ARNESH]
        assert [row["title"] for row in result["cited_by"]] == [RAVI]

    async def test_words_beside_the_reference_are_shown_as_words(self):
        result = await self.check("Arnesh Kumar v. State of Bihar")
        passage = result["cited_by"][0]["passages"][0]
        words = {item["word"]: item["cautionary"] for item in passage["words_near_reference"]}
        assert words == {"followed": False, "overruled": True}
        assert any("not a finding" in limit for limit in result["limits"])

    async def test_a_judgment_not_held_is_not_called_nonexistent(self):
        result = await self.check("Vishaka v. State of Rajasthan")
        assert result["held"] == []
        assert result["coverage"]["absence_note"] == "A judgment not found here is not evidence that none exists."
        assert result["coverage"]["judgments_held"] == 4

    async def test_statutory_currency_flags_the_repealed_code_it_relies_on(self):
        result = await self.check("State of Kerala v. K. Ajith")
        row = next(item for item in result["provisions"] if item["section"] == "321")
        assert row["code"] == "CrPC" and row["needs_attention"] is True
        assert row["finding"] in {"renumbered", "elements_changed", "no_mapping_known"}

    async def test_a_provision_lists_the_held_judgments_citing_it(self):
        result = await self.check("section 41 of the Code of Criminal Procedure")
        assert [row["title"] for row in result["cited_by_provision"]] == [ARNESH]
        assert result["provisions"][0]["citation"] == "CrPC s.41"

    async def test_a_bare_party_name_is_a_possible_match_and_says_so(self):
        result = await self.check("Arnesh Kumar")
        assert result["held"][0]["confidence"] == "possible"
        assert "Confirm" in result["held"][0]["match_note"]

    async def test_an_unreadable_index_raises_rather_than_reporting_nothing(self):
        client = FakeQdrant(corpus())
        client.fail = True
        with pytest.raises(CorpusUnavailable):
            await check_treatment(index=JudgmentIndex(client, "c", ttl_seconds=0), reference_text="Arnesh Kumar")


class TestOpponentCheck:
    FILING = (
        "The State relies on Arnesh Kumar v. State of Bihar, (2014) 8 SCC 273, for arrest being "
        "mechanical. Reliance is also placed on Vishaka v. State of Rajasthan. The accused is charged "
        "under Section 302 IPC and section 438 CrPC. Also section 124A of the Indian Penal Code."
    )

    async def test_a_held_case_shows_the_passage_nearest_the_proposition(self):
        result = await check_opponent_authorities(index=index(), text=self.FILING)
        arnesh = next(row for row in result["cases"] if "Arnesh" in row["reference"])
        assert arnesh["held"] is True
        assert "Arrest should not be mechanical" in arnesh["passages"][0]["excerpt"]
        assert arnesh["cited_in_held_judgments"] == 1

    async def test_a_case_not_held_says_nothing_about_whether_it_exists(self):
        result = await check_opponent_authorities(index=index(), text=self.FILING)
        vishaka = next(row for row in result["cases"] if "Vishaka" in row["reference"])
        assert vishaka["held"] is False
        assert "says nothing about whether it exists" in vishaka["not_found_note"]

    async def test_repealed_provisions_are_flagged_first(self):
        result = await check_opponent_authorities(index=index(), text=self.FILING)
        assert result["repealed_provisions"] == 3
        assert result["needs_attention"] >= 2
        assert result["provisions"][0]["needs_attention"] is True
        sedition = next(row for row in result["provisions"] if row["section"] == "124A")
        assert sedition["code"] == "IPC"

    async def test_it_states_how_many_judgments_it_compared_against(self):
        result = await check_opponent_authorities(index=index(), text=self.FILING)
        assert result["coverage"]["judgments_held"] == 4
        assert "not evidence" in result["coverage"]["absence_note"]

    async def test_it_still_checks_provisions_when_the_index_is_down(self):
        client = FakeQdrant(corpus())
        client.fail = True
        result = await check_opponent_authorities(index=JudgmentIndex(client, "c", ttl_seconds=0), text=self.FILING)
        assert result["coverage"]["judgments_held"] is None
        assert result["provisions"]
        assert all(row["held"] is False for row in result["cases"])


class TestReferenceParsing:
    def test_a_name_and_its_citation_are_one_reference(self):
        references = parse_case_references("See State of Kerala v. K. Ajith, (2022) 3 SCC 1, on this.")
        assert len(references) == 1
        assert references[0].first == "State of Kerala"
        assert references[0].citation == "(2022) 3 SCC 1"

    def test_a_citation_alone_is_kept(self):
        references = parse_case_references("Reliance is placed on 2024 INSC 123 for this.")
        assert references[0].citation == "2024 INSC 123"
        assert references[0].first is None

    def test_a_leading_see_is_not_a_party(self):
        assert parse_case_references("See Ram Kumar vs Shyam Lal.")[0].first == "Ram Kumar"

    def test_title_splitting_drops_the_case_number(self):
        assert split_title(AJITH) == ("THE STATE OF KERALA", "K.AJITH")
        assert split_title("Nothing to split here") is None

    @pytest.mark.parametrize(
        ("first", "second", "expected"),
        [
            ("Kerala", "K. Ajith", True),
            ("K. Ajith", "State of Kerala", True),
            ("State", "Union of India", False),
            ("Someone Else", "State of Kerala", False),
        ],
    )
    def test_matching_needs_something_distinctive(self, first, second, expected):
        assert match_parties(first, second, "THE STATE OF KERALA", "K.AJITH").matched is expected


def test_coverage_of_nothing_is_zero_not_absent():
    coverage = coverage_of([])
    assert coverage.judgments_held == 0
    assert "the 0 judgments" in coverage_statement(coverage)["statement"]
