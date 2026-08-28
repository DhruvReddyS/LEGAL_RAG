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


def extract_pdf(
    path: Path,
    *,
    document_id: str,
    minimum_page_characters: int = 40,
    ocr_language: str = "eng",
    ocr_dpi: int = 300,
    ocr_workers: int = 4,
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
