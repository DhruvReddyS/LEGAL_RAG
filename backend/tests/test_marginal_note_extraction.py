"""Marginal notes must not be woven through the section they annotate.

Indian bare Acts print each section's marginal note in a narrow left column.
Read line by line, the note arrives welded to the front of every body line, so
the section's own sentence cannot be quoted or verified against the source.
These tests work on synthetic word boxes -- (x0, y0, x1, y1, word, ...), the
shape PyMuPDF returns -- so they describe the geometry rather than one PDF.
"""

from __future__ import annotations

from app.ingestion.extract import marginal_note_boundary, unwoven_page_text


PAGE_WIDTH = 595.0
NOTE_X, BODY_X = 58.0, 150.0


def _line(top: float, note: str, body: str) -> list[tuple]:
    """One printed line: a marginal fragment on the left, body text right of it."""
    words = []
    x = NOTE_X
    for word in note.split():
        words.append((x, top, x + 4.5 * len(word), top + 9, word, 0, 0, 0))
        x += 4.5 * len(word) + 3
    x = BODY_X
    for word in body.split():
        words.append((x, top, x + 6 * len(word), top + 9, word, 0, 0, 0))
        x += 6 * len(word) + 4
    return words


# A page shaped like a printed one: a few marginal notes down the left, and a
# body of many more lines. The proportion matters -- the detector refuses to
# cut a page where the left band carries as much text as the right.
SECTION = (
    _line(100, "Disposal", "437. (1) When a question has been so referred, the High Court")
    + _line(112, "of case", "shall pass such order thereon as it thinks fit, and shall cause a")
    + _line(124, "to High", "copy of such order to be sent to the Court by which the reference")
    + _line(136, "Court.", "was made, which shall dispose of the case conformably.")
    + _line(160, "Costs.", "(2) The High Court may direct by whom the costs shall be paid.")
    + [
        word
        for index in range(18)
        for word in _line(172 + index * 12, "", f"Body line {index} continuing the section without a note.")
    ]
)


def test_the_section_reads_as_one_unbroken_sentence() -> None:
    text = unwoven_page_text(SECTION, PAGE_WIDTH)
    assert text is not None
    body = " ".join(
        line for line in text.splitlines() if not line.startswith(("Disposal", "Costs."))
    )
    # The sentence a citation would quote, with nothing spliced into it.
    assert (
        "437. (1) When a question has been so referred, the High Court shall pass "
        "such order thereon as it thinks fit, and shall cause a copy of such order "
        "to be sent to the Court by which the reference was made, which shall "
        "dispose of the case conformably."
    ) in " ".join(body.split())


def test_the_note_survives_whole_and_above_its_section() -> None:
    text = unwoven_page_text(SECTION, PAGE_WIDTH)
    assert text is not None
    lines = text.splitlines()
    assert lines[0] == "Disposal of case to High Court."
    assert lines[1].startswith("437.")
    # Emitted once, not once per body line it happened to touch.
    assert sum(1 for line in lines if "Disposal" in line) == 1


def test_a_page_with_no_marginal_column_is_left_alone() -> None:
    single_column = []
    for index in range(14):
        single_column += _line(100 + index * 12, "", f"Body line {index} of an ordinary page.")
    assert marginal_note_boundary(single_column, PAGE_WIDTH) is None
    assert unwoven_page_text(single_column, PAGE_WIDTH) is None


def test_a_word_across_the_gutter_joins_the_column_holding_most_of_it() -> None:
    """Words are split by where their middle sits, not by an edge.

    Every word lands in exactly one column, so none can be lost; what the
    midpoint buys is that a word printed across the gutter joins the column
    it mostly occupies instead of being pushed into the body mid-sentence.
    """
    # Boundary lands near 122. This word runs 90 -> 130, so most of it is in
    # the note column even though its right edge crosses.
    straddler = (90.0, 148.0, 130.0, 157.0, "STRADDLER", 0, 0, 0)
    page = SECTION + [straddler] + _line(148, "", "and the body continues here.")
    text = unwoven_page_text(page, PAGE_WIDTH)
    assert text is not None
    assert "STRADDLER" in text.split(), "no word may be dropped at the gutter"
    line = next(line for line in text.splitlines() if "STRADDLER" in line)
    assert "and the body continues here." not in line, (
        "a word that mostly sits in the note column must not be spliced into the body"
    )


def test_a_narrow_left_column_of_body_text_is_not_cut_away() -> None:
    """The left band is a minority of the words but is written on as many
    lines as the body, which is what a column of body text looks like. Only
    the line-count contrast separates this from a page of marginal notes."""
    page = []
    for index in range(20):
        top = 100 + index * 12
        page += _line(top, "left text", "right column body text continuing here for a while")
    words = [w for w in page if (w[0] + w[2]) / 2 <= 118]
    share = len(words) / len(page)
    assert 0.004 <= share <= 0.30, f"share {share:.3f} must land inside the accepted band"
    assert marginal_note_boundary(page, PAGE_WIDTH) is None


def test_a_left_band_holding_most_of_the_page_is_not_a_note_column() -> None:
    """A narrow left band written on few lines looks like marginal notes by
    line count, but it holds most of the words on the page. Only the share
    check sees that the left band is carrying the text, not annotating it."""
    page = []
    for index in range(8):
        page += _line(100 + index * 12, "aa bb cc", "z")
    for index in range(40):
        page += _line(200 + index * 12, "", "z")
    left = [w for w in page if (w[0] + w[2]) / 2 <= 118]
    assert len(left) / len(page) > 0.30, "the fixture must exceed the accepted share"
    assert marginal_note_boundary(page, PAGE_WIDTH) is None
