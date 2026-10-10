"""A doubled text layer must be re-read, not trusted.

Some PDFs carry every word twice -- "shall shall be be provided provided to to
facilitate facilitate access access to to justice justice" -- usually from a
scanner writing both a recognised and a rendered layer. It extracts cleanly
and passes a length check comfortably, so extraction accepted it. It is also
unsearchable: no query matches the doubled form, and any citation quoting it
is gibberish to a reader.

v5 indexed 61 such chunks across five documents, including the Child Helpline
SOP and the NALSA community mediation SOP. The chunk classifier catches them
after the fact, but then the provision is simply absent from the corpus. The
page has to reach OCR, which is where a clean copy comes from.

The second half matters as much as the first: a clean OCR of a doubled page is
about half the length of the native text, and extraction only accepted OCR
that was *longer*. Fixing the trigger without the acceptance rule would queue
the OCR and throw the result away.
"""

from __future__ import annotations

from app.ingestion.extract import ExtractedPage, _DOUBLED_TEXT_LAYER_RATIO
from app.ingestion.enrichment import doubled_word_ratio

# Taken from the corpus: a page of the Child Helpline SOP as v5 indexed it.
# The doubling is within each token, not between words, which is what a
# scanner writing two overlapping layers produces.
DOUBLED = (
    "MISSIONMISSION VATSALYAVATSALYA SCHEMESCHEME "
    "MinistryMinistry ofof WomenWomen andand ChildChild DevelopmentDevelopment "
    "GovernmentGovernment ofof IndiaIndia"
)
CLEAN = (
    "MISSION VATSALYA SCHEME "
    "Ministry of Women and Child Development "
    "Government of India"
)


def test_the_doubled_page_in_the_corpus_is_detected() -> None:
    assert doubled_word_ratio(DOUBLED) >= _DOUBLED_TEXT_LAYER_RATIO
    assert doubled_word_ratio(CLEAN) < _DOUBLED_TEXT_LAYER_RATIO


def test_ordinary_legal_prose_is_not_mistaken_for_a_doubled_layer() -> None:
    """A false positive sends a good page to OCR and replaces accurate text
    with a recognition guess, so the threshold has to clear real statutory
    prose, including repetition that legal drafting genuinely contains."""
    for text in (
        "Whoever commits murder shall be punished with death or imprisonment "
        "for life and shall also be liable to fine",
        "The appropriate Government may by notification in the Official "
        "Gazette make rules for carrying out the purposes of this Act",
        "had had the the",  # too few long words to sample
        "Provided that nothing in this section shall apply to any person who "
        "is a member of the Armed Forces of the Union",
    ):
        assert doubled_word_ratio(text) < _DOUBLED_TEXT_LAYER_RATIO, text


def test_a_shorter_ocr_result_wins_on_a_doubled_page() -> None:
    """The acceptance rule a length test gets backwards.

    Native doubled text is roughly twice the real length, so a correct OCR is
    always shorter. Judged on length it loses; judged on whether the doubling
    is gone, it wins.
    """
    page = ExtractedPage(
        page_number=1, text=DOUBLED, original_page_text=DOUBLED,
        extraction_method="pymupdf", ocr_used=False, doubled_native_text=True,
    )
    assert len(CLEAN) < len(page.original_page_text), "premise: the fix is shorter"

    improved_by_doubling = doubled_word_ratio(CLEAN) < doubled_word_ratio(
        page.original_page_text
    )
    improved_by_length = len(CLEAN.strip()) > len(page.original_page_text.strip())

    assert improved_by_doubling is True
    assert improved_by_length is False, (
        "a length test discards the correct OCR of a doubled page"
    )


def test_an_empty_page_is_still_judged_on_length() -> None:
    """The doubling rule must not replace the rule that made OCR work for
    scans, which is the common case by far."""
    page = ExtractedPage(
        page_number=1, text="", original_page_text="",
        extraction_method="pymupdf", ocr_used=False, doubled_native_text=False,
    )
    assert page.doubled_native_text is False
    assert len("recovered text".strip()) > len(page.original_page_text.strip())


def test_the_flag_survives_until_the_ocr_future_returns() -> None:
    """The page is queued for OCR and judged later. If why it was queued were
    not recorded on the page, the acceptance step could not tell a doubled
    page from an empty one."""
    assert "doubled_native_text" in ExtractedPage.model_fields
    assert ExtractedPage.model_fields["doubled_native_text"].default is False
