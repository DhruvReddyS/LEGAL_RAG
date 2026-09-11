from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel, Field

from app.ingestion.ocr import ocr_png


class ExtractedPage(BaseModel):
    page_number: int = Field(ge=1)
    text: str
    original_page_text: str
    extraction_method: str
    ocr_used: bool
    warnings: list[str] = Field(default_factory=list)


class ExtractedDocument(BaseModel):
    document_id: str
    source_path: str
    pages: list[ExtractedPage]
    warnings: list[str] = Field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text.strip())


# Indian bare Acts are printed with the section's marginal note in a narrow
# left column. PyMuPDF's sorted text walks the page line by line, so each body
# line arrives with a fragment of that note welded to its front:
#
#     Disposal of      437. (1) When a question has been so referred, the High
#     case according   Court shall pass such order thereon as it thinks fit, and
#
# The sentence is then unquotable, which matters because verification checks
# extracts against the source text and citations show the passage to a reader.
# Splitting the columns puts the note back where a reader expects it -- whole,
# immediately above the section it names.

# The columns must be separated by a real gutter, and the note column must be
# a minority of the page. Outside those bounds we are not looking at marginal
# notes and must not cut the page up.
_MIN_GUTTER_POINTS = 6.0
# The body is written on far more lines than the notes beside it. Requiring
# that contrast is what stops a genuine two-column body being cut in half.
_MIN_BODY_TO_NOTE_LINES = 2.0
# A page carrying a single short note still carries it in a column, and the
# gutter and contrast tests already reject noise.
_MIN_MARGIN_SHARE = 0.004
_MAX_MARGIN_SHARE = 0.30
# Marginal note lines sit close together; a larger drop starts the next note.
_NOTE_BREAK_POINTS = 16.0
_ROW_TOLERANCE_POINTS = 3.0


def marginal_note_boundary(words: list, page_width: float) -> float | None:
    """The x where the marginal-note column ends, or None if there is none.

    Found by geometry rather than by guessing at indents: a marginal note is a
    narrow band of text on the left, then a gutter that the great majority of
    lines leave empty, then the body. Two details make or break this. Coverage
    is counted in lines, not words, because one full-width rule in the running
    header would otherwise paint over the gutter and hide it. And the gutter
    must be a run several points wide, because the ordinary spaces between
    words leave gaps a point or two across on every line.
    """
    if len(words) < 20:
        return None
    lines = _rows(words)
    if len(lines) < 6:
        return None

    width = int(page_width) + 1
    coverage = [0] * width
    for _, row in lines:
        spanned = set()
        for word in row:
            spanned.update(range(max(0, int(word[0])), min(width - 1, int(word[2])) + 1))
        for x in spanned:
            coverage[x] += 1

    # A rule, a page number or a stray footnote marker should not count as
    # the column being occupied.
    floor = max(1, int(len(lines) * 0.08))
    occupied = [hits > floor for hits in coverage]

    band_start = next((x for x, hit in enumerate(occupied) if hit), None)
    if band_start is None:
        return None

    boundary = None
    x = band_start
    while x < width:
        if occupied[x]:
            x += 1
            continue
        run_end = x
        while run_end < width and not occupied[run_end]:
            run_end += 1
        if run_end >= width:
            break
        if run_end - x >= _MIN_GUTTER_POINTS:
            if x > page_width / 3:
                return None
            boundary = (x + run_end) / 2
            break
        x = run_end
    if boundary is None:
        return None

    note_band = max(coverage[band_start:int(boundary)] or [0])
    body_band = max(coverage[int(boundary):] or [0])
    if note_band == 0 or body_band < note_band * _MIN_BODY_TO_NOTE_LINES:
        return None

    share = sum(1 for word in words if _is_margin(word, boundary)) / len(words)
    if not _MIN_MARGIN_SHARE <= share <= _MAX_MARGIN_SHARE:
        return None
    return boundary


def _is_margin(word: tuple, boundary: float) -> bool:
    """Which column a word belongs to, by where most of it sits.

    Testing an edge instead would drop any word straddling the boundary, and
    a corpus that silently loses words of statute is worse than one that
    leaves the columns woven together.
    """
    return (word[0] + word[2]) / 2 <= boundary


def _rows(words: list) -> list[tuple[float, list]]:
    grouped: dict[int, list] = {}
    for word in words:
        grouped.setdefault(round(word[1] / _ROW_TOLERANCE_POINTS), []).append(word)
    return [
        (key * _ROW_TOLERANCE_POINTS, sorted(row, key=lambda word: word[0]))
        for key, row in sorted(grouped.items())
    ]


def unwoven_page_text(words: list, page_width: float) -> str | None:
    """Page text with each marginal note lifted out whole, or None if absent."""
    boundary = marginal_note_boundary(words, page_width)
    if boundary is None:
        return None

    notes: list[tuple[float, str]] = []
    lines: list[str] = []
    note_top: float | None = None
    previous: float | None = None
    for top, row in _rows([word for word in words if _is_margin(word, boundary)]):
        if previous is not None and top - previous > _NOTE_BREAK_POINTS and lines:
            notes.append((note_top or top, " ".join(lines)))
            lines, note_top = [], None
        if note_top is None:
            note_top = top
        lines.append(" ".join(word[4] for word in row))
        previous = top
    if lines:
        notes.append((note_top or 0.0, " ".join(lines)))

    out: list[str] = []
    pending = list(notes)
    for top, row in _rows([word for word in words if not _is_margin(word, boundary)]):
        # A note introduces the section beside it, so it is emitted before the
        # first body line it reaches rather than at every line it touches.
        while pending and pending[0][0] <= top + _ROW_TOLERANCE_POINTS * 2:
            out.append(pending.pop(0)[1])
        out.append(" ".join(word[4] for word in row))
    out.extend(note for _, note in pending)
    return "\n".join(out)


def extract_pdf(
    path: Path,
    *,
    document_id: str,
    minimum_page_characters: int = 40,
    ocr_language: str = "eng",
    ocr_dpi: int = 300,
    ocr_workers: int = 4,
    ocr_timeout: float = 0,
) -> ExtractedDocument:
    """Extract with PyMuPDF and OCR only pages whose native text is insufficient."""
    import pymupdf as fitz

    pages: list[ExtractedPage] = []
    pending_ocr: list[tuple[int, Future[str]]] = []
    with ThreadPoolExecutor(max_workers=max(1, ocr_workers)) as executor:
        with fitz.open(path) as pdf:
            for page_index, page in enumerate(pdf):
                warnings: list[str] = []
                native_text = page.get_text("text", sort=True)
                unwoven = unwoven_page_text(page.get_text("words"), page.rect.width)
                if unwoven is not None:
                    native_text = unwoven
                pages.append(
                    ExtractedPage(
                        page_number=page_index + 1,
                        text=native_text,
                        original_page_text=native_text,
                        extraction_method="pymupdf",
                        ocr_used=False,
                        warnings=warnings,
                    )
                )
                if len(native_text.strip()) < minimum_page_characters:
                    pages[-1].warnings.append(
                        f"Native extraction yielded fewer than {minimum_page_characters} characters"
                    )
                    try:
                        scale = ocr_dpi / 72
                        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                        pending_ocr.append(
                            (
                                page_index,
                                executor.submit(
                                    ocr_png,
                                    pixmap.tobytes("png"),
                                    language=ocr_language,
                                    **({"timeout": ocr_timeout} if ocr_timeout else {}),
                                ),
                            )
                        )
                    except Exception as exc:
                        pages[-1].warnings.append(
                            f"OCR rendering failed: {type(exc).__name__}: {exc}"
                        )

        for page_index, future in pending_ocr:
            page_result = pages[page_index]
            try:
                ocr_text = future.result()
                if len(ocr_text.strip()) > len(page_result.original_page_text.strip()):
                    page_result.text = ocr_text
                    page_result.extraction_method = "tesseract"
                    page_result.ocr_used = True
                else:
                    page_result.warnings.append("OCR did not improve extracted text")
            except Exception as exc:
                page_result.warnings.append(f"OCR failed: {type(exc).__name__}: {exc}")
            if not page_result.text.strip():
                page_result.warnings.append("Page has no extractable text")
    document_warnings = [
        f"page {page.page_number}: {warning}"
        for page in pages
        for warning in page.warnings
    ]
    if not pages:
        document_warnings.append("PDF contains no pages")
    return ExtractedDocument(
        document_id=document_id,
        source_path=str(path),
        pages=pages,
        warnings=document_warnings,
    )
