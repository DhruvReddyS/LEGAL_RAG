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

    def test_the_marginal_note_becomes_the_section_title(self) -> None:
        units = parse_legal_structure(
            _document(
                ["Definitions.            2. (1) In this Sanhita, unless the context requires,—"]
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
            ["      35. (1) Any police officer may without an order from a Magistrate arrest"]
        )

    def test_a_lettered_section_is_captured(self) -> None:
        assert "41A" in _sections(
            ["Notice of appearance.   41A. (1) The police officer shall issue a notice"]
        )


class TestTheHeadingFirstLayoutStillWorks:
    """The IPC keeps 93% of its sections under the old patterns. This change
    must not cost that."""

    def test_a_conventional_numbered_section(self) -> None:
        assert "378" in _sections(["378. Theft.", "Whoever, intending to take dishonestly"])

    def test_a_column_layout_section(self) -> None:
        assert "302" in _sections(["Punishment for murder.        302. Punishment for murder"])


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
