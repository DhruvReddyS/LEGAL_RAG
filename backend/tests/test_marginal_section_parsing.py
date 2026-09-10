"""The layout the 2023 Sanhitas are printed in.

Half the BNSS was invisible to retrieval because of one parser assumption. The
two existing patterns require the section title to follow the number:

    14. Subordination of Executive Magistrates.

The Sanhitas print the title as a marginal note in a side column, so
extraction interleaves it and what follows the number is the sub-section
marker instead:

    Definitions.            2. (1) In this Sanhita, unless the context ...

"(" is not "[A-Z]", so neither pattern matched. 271 of 531 BNSS sections were
present in the extracted text and absent from every query that needed them.
The IPC, typeset heading-first, kept 93% of its sections -- which is why the
corpus looked systematically richer in repealed law than in current law.
"""

from __future__ import annotations

import pytest

from app.ingestion.extract import ExtractedDocument, ExtractedPage
from app.ingestion.structure import parse_legal_structure
from app.ingestion.classifier import LegalDocumentType


def _document(lines: list[str]) -> ExtractedDocument:
    return ExtractedDocument(
        document_id="doc-1",
        source_path="bnss.pdf",
        pages=[
            ExtractedPage(
                page_number=1,
                text="\n".join(lines),
                original_page_text="\n".join(lines),
                extraction_method="text",
                ocr_used=False,
            )
        ],
    )


def _sections(lines: list[str]) -> set[str]:
    units = parse_legal_structure(_document(lines), LegalDocumentType.ACT)
    return {unit.section for unit in units if unit.section}


class TestTheMarginalNoteLayout:
    def test_a_section_followed_by_a_subsection_marker_is_captured(self) -> None:
        """The exact shape that was being dropped."""
        sections = _sections(
            [
                "Definitions.            2. (1) In this Sanhita, unless the context otherwise requires,—",
                "                        3. (1) Unless the context otherwise requires, any reference in any law",
            ]
        )

        assert {"2", "3"} <= sections

    def test_common_gazette_ocr_variants_are_captured(self) -> None:
        sections = _sections(
            [
                "Short title.       1.(/) This Act may be called the Example Act.",
                "                 18: (/) Any person aggrieved may appeal.",
                "Appropriate Government       24. The Government may publish guidance.",
                "हटाने की शक्ति       30. (/) The Government may remove difficulties.",
            ]
        )
        assert {"1", "18", "24", "30"} <= sections

    def test_gazette_ocr_variants_are_captured(self) -> None:
        sections = _sections(
            [
                "Complaint of        9, (/) Any aggrieved woman may make a complaint",
                "Inquiry            11. (I) Subject to section 10, the Committee shall inquire",
            ]
        )

        assert {"9", "11"} <= sections

    def test_the_marginal_note_becomes_the_section_title(self) -> None:
        units = parse_legal_structure(
            _document(
                [
                    "Definitions.            2. (1) In this Sanhita, unless the context requires,—"
                ]
            ),
            LegalDocumentType.ACT,
        )
        titled = [u for u in units if u.section == "2"]

        assert titled
        assert "Definitions" in " ".join(titled[0].heading_path)

    def test_a_section_with_no_marginal_note_is_still_captured(self) -> None:
        """A section labelled without its title is retrievable. An unlabelled
        one is not, so the label matters more than the title."""
        assert "35" in _sections(
            [
                "      35. (1) Any police officer may without an order from a Magistrate arrest"
            ]
        )

    def test_a_lettered_section_is_captured(self) -> None:
        assert "41A" in _sections(
            ["Notice of appearance.   41A. (1) The police officer shall issue a notice"]
        )


class TestTheHeadingFirstLayoutStillWorks:
    """The IPC keeps 93% of its sections under the old patterns. This change
    must not cost that."""

    def test_a_conventional_numbered_section(self) -> None:
        assert "378" in _sections(
            ["378. Theft.", "Whoever, intending to take dishonestly"]
        )

    def test_a_column_layout_section(self) -> None:
        assert "302" in _sections(
            ["Punishment for murder.        302. Punishment for murder"]
        )


class TestItDoesNotInventSections:
    @pytest.mark.parametrize(
        "line",
        [
            "The court held in paragraph 12. (1) of the judgment that",
            "See page 45. (2) below for the schedule",
        ],
    )
    def test_prose_mentioning_a_number_is_not_a_section(self, line: str) -> None:
        """A false section splits a provision away from its own heading, which
        is worse than missing one -- the text becomes unretrievable by the
        query that needs it."""
        sections = _sections([line])

        # A false section splits a provision away from its own heading, which
        # is worse than missing one: the text becomes unretrievable by the
        # query that needs it. Prose mentioning a number must not create one.
        assert not sections


class TestTheMarginalNoteOftenHasNoFullStop:
    """The second half of the same defect, and the more costly half.

    Requiring the note to end in a period matched "Definitions.   2. (1) ..."
    and missed "Information    173. (1) ...". The note is a wrapped phrase in a
    narrow column and frequently carries no full stop at all, which left 134
    further sections unlabelled -- including BNSS s.173, the FIR provision, and
    s.35, which governs arrest without warrant. Deep was reasoning about arrest
    without ever seeing the section that authorises it.
    """

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            (
                "Information         173. (1) Every information relating to a cognizable offence",
                "173",
            ),
            (
                "Recording of         183. (1) Any Magistrate of the District in which",
                "183",
            ),
            (
                "When bail           480. (1) When any person accused of an offence",
                "480",
            ),
            (
                "Definitions.            2. (1) In this Sanhita, unless the context requires",
                "2",
            ),
            (
                "      35. (1) Any police officer may without an order from a Magistrate",
                "35",
            ),
        ],
    )
    def test_every_layout_in_the_sanhitas(self, line: str, expected: str) -> None:
        assert expected in _sections([line])

    def test_the_governing_arrest_provision_is_found(self) -> None:
        """The specific failure this traced back from: an answer about arrest
        without warrant whose evidence never contained BNSS s.35."""
        sections = _sections(
            [
                "When police         35. (1) Any police officer may without an order from a "
                "Magistrate and without a warrant arrest any person who commits a cognizable offence"
            ]
        )

        assert "35" in sections

    def test_prose_is_still_not_a_section(self) -> None:
        """Dropping the required full stop widens the pattern, so the negative
        direction is re-checked rather than assumed to hold."""
        for line in (
            "The court held in paragraph 12. (1) of the judgment that",
            "See page 45. (2) below for the schedule",
            "as noted in clause 7. (3) of the agreement",
        ):
            assert not _sections([line]), line
