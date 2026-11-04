"""Section labels must follow the Act, not whatever looks like a heading.

Every citation trusts this label, and a wrong one is invisible: the text still
comes back, under another number. The Contract Act's "15. Coercion" was cited as
s.12, and a footnote on the Specific Relief Act was cited as s.2.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion.classifier import LegalDocumentType
from app.ingestion.extract import ExtractedDocument, ExtractedPage
from app.ingestion.structure import parse_legal_structure


def _document(*pages: str) -> ExtractedDocument:
    return ExtractedDocument(
        document_id="doc",
        source_path="doc.pdf",
        pages=[
            ExtractedPage(
                page_number=number,
                text=text,
                original_page_text=text,
                extraction_method="native",
                ocr_used=False,
            )
            for number, text in enumerate(pages, 1)
        ],
    )


def _sections(*pages: str) -> dict[str, str]:
    units = parse_legal_structure(_document(*pages), LegalDocumentType.ACT)
    return {unit.section: unit.text for unit in units if unit.section}


def test_a_head_opening_with_a_quote_starts_its_own_section() -> None:
    sections = _sections(
        "12. What is a sound mind.\nA person is of sound mind.\n"
        '13. "Consent" defined.\nTwo persons are said to consent.\n'
        "14. Free consent defined.\nConsent is free.\n"
        "15. “Coercion” defined.\nCoercion is the committing of an act.\n"
    )
    assert "Coercion is" in sections["15"]
    assert "Coercion is" not in sections["12"]
    assert "Two persons" in sections["13"]


def test_a_head_opening_with_a_footnote_bracket_starts_its_own_section() -> None:
    sections = _sections(
        "33. Act and illegal omission.\nAn act.\n"
        "2[34. Acts done by several persons.\nIn furtherance of the common intention.\n"
        "35. When such an act is criminal.\nWhenever an act.\n"
    )
    assert "common intention" in sections["34"]


def test_a_footnote_is_not_a_section() -> None:
    sections = _sections(
        "20. Contracts specifically enforceable.\nThe court may enforce.\n"
        "2. Ins. by Act 52 of 1964, s. 3.\n(d) where the vendor sues.\n"
        "21. Power to award compensation.\nThe plaintiff may claim.\n"
    )
    assert "2" not in sections
    assert "where the vendor sues" in sections["20"]


def test_a_superscript_glued_to_the_number_is_read_through() -> None:
    sections = _sections(
        "150. Bailor's duty.\nThe bailor is bound.\n"
        "1151. Care to be taken by bailee.\nIn all cases of bailment.\n"
        "152. Bailee when not liable.\nThe bailee is not responsible.\n"
    )
    assert "In all cases of bailment" in sections["151"]
    assert "1151" not in sections


def test_a_year_is_not_a_section() -> None:
    sections = _sections(
        "5. Rules.\nThe Rules made in the year were called the Procedure\n"
        "1993. Rules of that name apply.\n"
        "6. Power to amend.\nThe Government may amend.\n"
    )
    assert "1993" not in sections


def test_a_short_numbered_list_inside_a_section_stays_inside_it() -> None:
    before = "".join(f"{number}. Provision {number}.\nIts text.\n" for number in range(40, 45))
    sections = _sections(
        before
        + "45. Duties.\nThe officer shall:\n"
        "1. Record the statement.\n2. Inform the person.\n3. Send the report.\n"
        "46. Power to arrest.\nThe officer may arrest.\n"
    )
    assert "Send the report" in sections["45"]
    assert set(sections) == {str(number) for number in range(40, 47)}


def test_prose_mentioning_a_section_does_not_open_it() -> None:
    sections = _sections(
        "12. Application.\nThe provisions of\n"
        "section 13 of the Code shall apply to these proceedings.\n"
        "Part III of the Constitution applies equally.\n"
        "13. Penalty.\nWhoever contravenes.\n"
    )
    assert "shall apply" in sections["12"]
    assert "applies equally" in sections["12"]


def test_a_number_alone_on_its_line_opens_the_next_section_only() -> None:
    sections = _sections(
        "5. Saving.\nNothing in this Sanhita shall affect any law other than this\n"
        "6.\nSanhita, there shall be Courts of Session.\n"
        "7. Territorial divisions.\nEvery State shall be divided.\n"
    )
    assert "Courts of Session" in sections["6"]

    far_ahead = _sections("5. Saving.\nText of it.\n40.\nNot the next section.\n")
    assert "40" not in far_ahead


def test_a_contents_page_is_not_a_set_of_sections() -> None:
    contents = "".join(f"{number}. Heading number {number}.\n" for number in range(1, 8))
    body = "".join(
        f"{number}. Heading number {number}.\n"
        + "The operative text of this provision runs on for long enough to be law. " * 3
        + "\n"
        for number in range(1, 8)
    )
    units = parse_legal_structure(_document(contents, body), LegalDocumentType.ACT)
    labelled_on_contents_page = [unit for unit in units if unit.section and unit.page_end == 1]
    assert not labelled_on_contents_page
    assert {unit.section for unit in units if unit.section} == {str(n) for n in range(1, 8)}


def test_schedule_entries_are_not_sections() -> None:
    filler = "".join(f"{number}. Provision number {number}.\nIts text.\n" for number in range(1, 10))
    sections = _sections(filler + "THE SCHEDULE\n40. Contempt of court.\n41. Fees.\n")
    assert "40" not in sections
    assert "41" not in sections


def test_a_contents_page_naming_a_schedule_does_not_silence_the_act() -> None:
    """How the Constitution lost 209 articles, and the CPC 144 sections."""
    filler = "Text of the arrangement of this enactment.\n" * 10
    sections = _sections(
        "THE FIRST SCHEDULE\n"
        + filler
        + "".join(f"{number}. Provision number {number}.\nIts text.\n" for number in range(1, 12))
    )
    assert "11" in sections


def test_two_instruments_in_one_file_keep_their_own_numbering() -> None:
    first = "".join(
        f"{number}. First rule {number}.\n" + "The text of the first instrument runs on. " * 4 + "\n"
        for number in range(1, 13)
    )
    second = "".join(
        f"{number}. Second rule {number}.\n" + "The text of the second instrument runs on. " * 4 + "\n"
        for number in range(1, 13)
    )
    units = parse_legal_structure(_document(first, second), LegalDocumentType.ACT)
    assert sum(1 for unit in units if unit.section == "5") == 2


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / "data/legal_kb/processed/extracted_text").is_dir(),
    reason="the extracted corpus is not in this checkout",
)
def test_the_major_acts_keep_their_sections() -> None:
    """The check that decides whether a rebuild is worth starting."""
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "check_section_coverage.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-1500:]


def test_a_window_cut_from_a_long_unit_reports_its_own_pages() -> None:
    from app.ingestion.chunker import _pages_of_span, _token_window_spans

    word = "statute "
    units = parse_legal_structure(
        _document(f"1. Long provision.\n{word * 600}\n", f"{word * 600}\n", f"{word * 600}\n"),
        LegalDocumentType.ACT,
    )
    unit = units[0]
    assert (unit.page_start, unit.page_end) == (1, 3)
    spans = _token_window_spans(unit.text, maximum_tokens=700, overlap_tokens=80)
    pages = [_pages_of_span(unit, *span) for span in spans]
    assert pages[0][0] == 1
    assert pages[-1][1] == 3
    assert all(last - first <= 1 for first, last in pages)
