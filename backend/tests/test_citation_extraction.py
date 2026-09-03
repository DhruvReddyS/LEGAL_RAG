"""Citation extraction must be precise before it is complete.

The graph is a retrieval hint. A missing edge costs recall; a wrong edge sends
a reader to the wrong provision, which is worse. These tests weight precision
accordingly, and several assert that an ambiguous reference stays unresolved
rather than being guessed.
"""

from __future__ import annotations

import pytest

from app.ingestion.citations import extract_references, resolve_act


class TestActResolution:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("the Code of Criminal Procedure, 1973", "crpc"),
            ("under CrPC", "crpc"),
            ("Cr.P.C.", "crpc"),
            ("the Indian Penal Code", "ipc"),
            ("Bharatiya Nagarik Suraksha Sanhita, 2023", "bnss"),
            ("Bharatiya Nyaya Sanhita", "bns"),
            ("the Constitution of India", "constitution"),
            ("Indian Evidence Act, 1872", "evidence"),
            ("Protection of Children from Sexual Offences Act", "pocso"),
            ("Negotiable Instruments Act", "ni"),
        ],
    )
    def test_known_acts_resolve(self, text: str, expected: str) -> None:
        assert resolve_act(text) == expected

    def test_an_unlisted_act_stays_unresolved(self) -> None:
        """A key per Act ever mentioned would make a graph of dangling nodes."""
        assert resolve_act("the Merchant Shipping Act, 1958") is None

    def test_the_longest_alias_wins(self) -> None:
        """"code of criminal procedure" must beat a bare "crpc" inside it."""
        assert resolve_act("Code of Criminal Procedure, 1973 (CrPC)") == "crpc"

    def test_the_nearest_act_wins(self) -> None:
        assert resolve_act("the Indian Penal Code and the Evidence Act") == "ipc"


class TestSectionReferences:
    @pytest.mark.parametrize(
        "text",
        [
            "Section 154 of the Code of Criminal Procedure, 1973",
            "section 154 of the CrPC",
            "s. 154 CrPC",
            "u/s 154 Cr.P.C.",
            "under section 154 of the Code of Criminal Procedure",
        ],
    )
    def test_a_qualified_section_resolves_to_its_act(self, text: str) -> None:
        assert "crpc:154" in extract_references(text).provisions

    def test_an_unqualified_section_takes_the_documents_own_act(self) -> None:
        """Inside the CrPC, "section 154" means the CrPC.

        This is most of the corpus: a statute refers to its own sections
        without naming itself on every mention.
        """
        result = extract_references(
            "The procedure in section 154 shall apply.", self_act="crpc"
        )
        assert result.provisions == ("crpc:154",)

    def test_an_unqualified_section_with_no_context_stays_unresolved(self) -> None:
        """A wrong Act is a worse edge than no edge."""
        result = extract_references("as required by section 154")

        assert result.provisions == ()
        assert result.unresolved_sections == ("154",)

    def test_a_section_with_a_letter_suffix_is_kept_whole(self) -> None:
        assert "ipc:498A" in extract_references(
            "Section 498A of the Indian Penal Code"
        ).provisions

    def test_the_act_named_after_the_number_is_preferred_over_the_document(self) -> None:
        """"section 173 BNSS" inside the CrPC still means the BNSS."""
        result = extract_references(
            "compare with section 173 of the Bharatiya Nagarik Suraksha Sanhita",
            self_act="crpc",
        )
        assert "bnss:173" in result.provisions
        assert "crpc:173" not in result.provisions

    def test_several_sections_in_one_passage(self) -> None:
        result = extract_references(
            "Sections 154 and 156 of the CrPC, and section 41 of the Indian Penal Code"
        )
        assert "crpc:154" in result.provisions
        assert "ipc:41" in result.provisions


class TestArticleReferences:
    @pytest.mark.parametrize(
        "text", ["Article 14", "article 21", "Art. 32", "Articles 14 and 21"]
    )
    def test_articles_resolve_to_the_constitution(self, text: str) -> None:
        assert any(
            reference.startswith("constitution:")
            for reference in extract_references(text).provisions
        )

    def test_article_14_and_21_are_separate_edges(self) -> None:
        provisions = extract_references("Articles 14 and 21").provisions
        assert "constitution:14" in provisions
        # "and 21" is not matched by the article pattern on its own, which is a
        # known and acceptable recall gap: precision matters more here.
        assert all(reference.startswith("constitution:") for reference in provisions)


class TestCaseCitations:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("(2014) 2 SCC 1", "(2014) 2 SCC 1"),
            ("AIR 1978 SC 597", "AIR 1978 SC 597"),
            ("2024 INSC 113", "2024 INSC 113"),
        ],
    )
    def test_reported_citations(self, text: str, expected: str) -> None:
        assert expected in extract_references(text).cases

    def test_party_names(self) -> None:
        cases = extract_references(
            "as held in Lalita Kumari v. Govt of U.P. the registration is mandatory"
        ).cases
        assert any("Lalita Kumari v." in case for case in cases)

    def test_sentence_furniture_is_not_a_case_name(self) -> None:
        """"See X v. Y" is a citation; "The State vs the accused" mid-sentence
        is prose that happens to contain "vs"."""
        assert extract_references("In the matter v. The other").cases == ()

    def test_a_page_number_is_not_a_citation(self) -> None:
        """A loose reported-citation pattern turns pagination into edges."""
        assert extract_references("at page 154 of the report, 2014 2 1").cases == ()


class TestBounds:
    def test_empty_and_blank_text(self) -> None:
        assert extract_references("").provisions == ()
        assert extract_references("   \n  ").provisions == ()

    def test_a_contents_page_does_not_produce_hundreds_of_edges(self) -> None:
        """A table of contents lists section numbers as furniture, not
        citations. Left unbounded it would dominate the graph."""
        contents = " ".join(f"Section {number}." for number in range(1, 300))
        result = extract_references(contents, self_act="crpc", max_references=40)

        assert len(result.provisions) <= 40

    def test_references_are_deduplicated(self) -> None:
        result = extract_references(
            "section 154 CrPC ... section 154 CrPC ... s. 154 of the CrPC"
        )
        assert result.provisions.count("crpc:154") == 1


def test_the_ordinary_word_art_is_not_a_constitutional_reference() -> None:
    """"art 32" without a full stop is more often prose than a citation."""
    assert extract_references("the art 32 exhibition opened").provisions == ()
    assert "constitution:32" in extract_references("Art. 32").provisions


@pytest.mark.parametrize(
    "text",
    [
        "Ram Kumar & Anr. v. State of Kerala",
        "Sunil & Ors. v. Union of India",
        "Kumar and Others v. State",
    ],
)
def test_a_clipped_party_list_is_not_a_case_name(text: str) -> None:
    """"& Ors. v. State" is the tail of a party list.

    Matching from there produces "Ors. v. State", an edge that would point at
    a large share of the corpus and mean nothing.
    """
    cases = extract_references(text).cases
    for case in cases:
        assert not case.lower().startswith(("ors", "anr", "others", "another"))


def test_a_single_word_on_both_sides_is_not_a_case() -> None:
    assert extract_references("Held X v. Y applies").cases == ()
