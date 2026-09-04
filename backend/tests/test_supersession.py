"""Repeal is a fact with a date and a successor, so it is a table.

The direction that matters most is the negative one: a circular *about* a
section of the Penal Code is not itself repealed law, and labelling it as such
would put a false "no longer in force" warning on a document that is in force.
"""

from __future__ import annotations

import pytest

from app.ingestion.supersession import replacement_for


class TestTheRepealedCodes:
    @pytest.mark.parametrize(
        ("name", "expected_successor"),
        [
            ("The Indian Penal Code Act, 1860", "Bharatiya Nyaya Sanhita"),
            (
                "The Code of Criminal Procedure, 1973 (Act No.2 of 1974) 1996",
                "Bharatiya Nagarik Suraksha Sanhita",
            ),
            ("The Indian Evidence Act, 1872 1977 Accessible_Part_1", "Bharatiya Sakshya Adhiniyam"),
            ("The Code of Criminal Procedure (Amendment) Act, 2010", "Bharatiya Nagarik Suraksha Sanhita"),
        ],
    )
    def test_each_names_its_successor(self, name: str, expected_successor: str) -> None:
        result = replacement_for(name)

        assert result is not None, name
        assert expected_successor in result.replaced_by
        assert result.repealed_on == "2024-07-01"

    def test_the_1898_code_was_replaced_by_the_1973_code_not_the_sanhita(self) -> None:
        """The case a heuristic gets wrong.

        Both the general rule and this one match the title, so ordering is the
        whole of the correctness here. The 1898 Code was repealed fifty years
        before the Sanhita existed.
        """
        result = replacement_for("The Code of Criminal Procedure, 1898 (Sections 1 to 176) 1967")

        assert result is not None
        assert result.replaced_by == "The Code of Criminal Procedure, 1973"
        assert result.repealed_on == "1974-04-01"


class TestDocumentsThatAreNotRepealed:
    @pytest.mark.parametrize(
        "name",
        [
            # Circulars and advisories that cite a repealed code but are not it.
            "Advisory on measures to be taken by States/UTs to curb misuse of section 498A IPC",
            "Guidelines under the Code of Criminal Procedure for victim compensation",
            "Model Prison Manual, 2016",
            "THE BHARATIYA NYAYA SANHITA, 2023",
            "THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023",
            "The Protection of Children from Sexual Offences Act, 2012",
            "The Constitution of India",
            "",
        ],
    )
    def test_they_carry_no_repeal_label(self, name: str) -> None:
        assert replacement_for(name) is None, name

    def test_a_curated_act_name_beats_a_scraped_title(self) -> None:
        """Titles are scraped from download pages and are often furniture."""
        result = replacement_for(
            "The Indian Penal Code Act, 1860", "Accessible_Vol_01(PDF 4.15MB)"
        )

        assert result is not None
        assert "Bharatiya Nyaya Sanhita" in result.replaced_by

    def test_an_empty_name_is_skipped_rather_than_matched(self) -> None:
        result = replacement_for(None, "", "The Indian Penal Code Act, 1860")

        assert result is not None
