"""The quality classifier is the riskiest thing in ingestion.

It removes about a fifth of the index. A false positive deletes a provision a
citizen might need, and the deletion is silent. Every test below that asserts
something is *kept* matters more than the ones asserting rejection.
"""

from __future__ import annotations

import pytest

from app.ingestion.enrichment import (
    build_embed_text,
    classify_quality,
    structural_role,
)


class TestQualityRejects:
    @pytest.mark.parametrize(
        ("text", "reason"),
        [
            ("7.   CASES AGAINST HIGH GOVERNMENT       14 - 15", "table_of_contents"),
            ("1. Short title ........................ 7", "table_of_contents"),
            ('8.   Subs. by s. 2 and Sch. I, ibid., for "or Naval".', "amendment_footnote"),
            ("3. Subs. by s. 5, ibid., for “her heirs” (w.e.f. 19-11-1986).", "amendment_footnote"),
            ("No.V-17013/9/2006-PR", "reference_number"),
            ("F.No. 11012/1/2019", "reference_number"),
            ("CHAPTER II", "bare_heading"),
            ("PART III", "bare_heading"),
            ("THE FIRST SCHEDULE", "bare_heading"),
            ("   ", "empty"),
            ("47", "page_artefact"),
            ("[ 12 ]", "page_artefact"),
        ],
    )
    def test_furniture_is_rejected_with_a_reason(self, text: str, reason: str) -> None:
        result = classify_quality(text)

        assert result.quality == "noise", text
        assert result.reason == reason


class TestQualityKeeps:
    @pytest.mark.parametrize(
        "text",
        [
            # The provision that started all of this.
            "14. Equality before law.—The State shall not deny to any person "
            "equality before the law or the equal protection of the laws within "
            "the territory of India.",
            # A one-line definition clause: short, and unambiguously a provision.
            '"Court" means a Civil Court.',
            "In this Act, unless the context otherwise requires, “prescribed” "
            "means prescribed by rules made under this Act.",
            # Operative language without a section number.
            "Whoever commits theft shall be punished with imprisonment.",
            "No person shall be deprived of his life or personal liberty.",
            # Ordinary substantive prose.
            "The officer in charge of a police station shall reduce the "
            "information to writing.",
        ],
    )
    def test_real_legal_content_survives(self, text: str) -> None:
        assert classify_quality(text).quality == "indexed", text

    def test_a_short_numbered_provision_is_kept(self) -> None:
        """A section label is enough to keep a short chunk.

        This is the escape hatch that stops the length rule deleting genuine
        one-line provisions.
        """
        assert classify_quality("Repealed.", section="14").quality == "indexed"

    def test_omitted_alone_is_not_an_amendment_footnote(self) -> None:
        """"Omitted" appears in real provisions about omitted particulars.

        Only paired with an editorial marker like "ibid" or "w.e.f." does it
        indicate a footnote recording a legislative change.
        """
        text = "Omitted particulars shall be supplied by the informant on demand."
        assert classify_quality(text).quality == "indexed"

    def test_a_long_chapter_body_is_not_a_bare_heading(self) -> None:
        text = (
            "CHAPTER II deals with the powers of the police to investigate "
            "cognizable offences and prescribes the procedure to be followed."
        )
        assert classify_quality(text).quality == "indexed"


class TestStructuralRole:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Provided that no such order shall be made.", "proviso"),
            ("Explanation.—For the purposes of this section, ...", "explanation"),
            ("Illustration (a) A finds a purse.", "illustration"),
            ('"Court" means a Civil Court.', "definition"),
            ("THE FIRST SCHEDULE — offences under the Act", "schedule"),
        ],
    )
    def test_roles_from_text(self, text: str, expected: str) -> None:
        assert structural_role(text) == expected

    @pytest.mark.parametrize(
        ("unit_kind", "expected"),
        [
            ("facts", "facts"),
            ("issues", "issues"),
            ("appellant_arguments", "arguments"),
            ("respondent_arguments", "arguments"),
            ("court_analysis", "reasoning"),
            ("ratio", "ratio"),
            ("final_order", "order"),
        ],
    )
    def test_judgment_roles_come_from_the_parser(self, unit_kind, expected) -> None:
        """Advocate needs a judgment's ratio separated from its facts."""
        assert structural_role("some text", unit_kind=unit_kind) == expected

    def test_a_numbered_section_defaults_to_provision(self) -> None:
        assert structural_role("The State shall not deny...", section="14") == "provision"

    def test_unlabelled_text_is_prose(self) -> None:
        assert structural_role("Some general commentary.") == "prose"


class TestEmbedText:
    def test_the_motivating_case(self) -> None:
        """Bare, this chunk is four words. That is what made it unfindable."""
        embedded = build_embed_text(
            "14. Equality before law.",
            title="The Constitution of India (English, as on 1 May 2024)",
            heading_path=["Part III — Fundamental Rights"],
            section="14",
        )

        assert "Constitution of India" in embedded
        assert "Fundamental Rights" in embedded
        assert "Section 14" in embedded
        assert embedded.endswith("14. Equality before law.")

    def test_the_quoted_text_is_never_modified(self) -> None:
        """A citation must quote the provision, not the prefix."""
        original = "The State shall not deny to any person equality before the law."
        embedded = build_embed_text(original, act_name="Constitution of India")

        assert original in embedded
        assert embedded != original

    def test_act_name_is_preferred_over_title(self) -> None:
        embedded = build_embed_text(
            "text",
            title="Accessible_Vol_01 scan of the Code",
            act_name="Code of Criminal Procedure, 1973",
        )
        assert embedded.startswith("Code of Criminal Procedure, 1973")

    def test_a_heading_already_in_the_name_is_not_repeated(self) -> None:
        embedded = build_embed_text(
            "text",
            act_name="The Indian Evidence Act, 1872",
            heading_path=["The Indian Evidence Act, 1872"],
        )
        assert embedded.count("Indian Evidence Act") == 1

    def test_the_prefix_cannot_outweigh_the_provision(self) -> None:
        """A prefix longer than its text makes every chunk of one Act alike."""
        embedded = build_embed_text(
            "Short provision.",
            act_name="A" * 400,
            heading_path=["B" * 400],
            section="1",
        )
        prefix = embedded.split(" — Short provision.")[0]
        assert len(prefix) <= 180

    def test_no_metadata_leaves_the_text_alone(self) -> None:
        assert build_embed_text("Bare text.") == "Bare text."

    def test_empty_text_stays_empty(self) -> None:
        assert build_embed_text("", act_name="Some Act") == ""


def test_a_chunk_that_opens_with_a_footnote_but_carries_on_is_kept() -> None:
    """Chunk boundaries do not respect footnotes.

    A chunk can begin with an editorial note and continue into the provision
    that note annotates. Rejecting on the opening alone discards the provision.
    """
    text = (
        '2. Subs. ibid., for "Zila Judge". '
        "or, if the document is to be produced or delivered to a court, the "
        "officer shall record the substance of the information in writing and "
        "shall furnish a copy to the informant without charge."
    )
    assert classify_quality(text).quality == "indexed"


def test_a_bare_footnote_is_still_rejected() -> None:
    text = "1. Ins. by the Constitution (Sixteenth Amendment) Act, 1963, s. 5 (w.e.f. 5-10-1963)."
    result = classify_quality(text)
    assert result.quality == "noise"
    assert result.reason == "amendment_footnote"
