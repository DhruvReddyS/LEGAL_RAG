"""Ephemeral citizen document extraction; never adds personal files to the corpus."""
from __future__ import annotations

import asyncio
import io
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from app.core.security import get_current_user
from app.ingestion.extract import extract_pdf
from app.ingestion.ocr import ocr_png
from app.models import User
from app.services.rate_limit import RateLimitExceeded, user_rate_limiter

router = APIRouter(prefix="/citizen/documents", tags=["citizen-intake"])
MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 20
MAX_TEXT = 12000
extraction_slots = asyncio.Semaphore(2)


def extract_upload(content: bytes, content_type: str) -> tuple[list[dict], bool]:
    """Temporary files are removed before returning, including on extraction failure."""
    if content_type == "application/pdf":
        import pymupdf as fitz
        with fitz.open(stream=content, filetype="pdf") as pdf:
            if pdf.needs_pass:
                raise ValueError("Password-protected PDFs are not supported")
            if len(pdf) > MAX_PAGES:
                raise ValueError("Please upload a PDF of 20 pages or fewer")
            if any(page.rect.width * page.rect.height * (150 / 72) ** 2 > 20_000_000 for page in pdf):
                raise ValueError("PDF page dimensions exceed the image-processing limit")
        with tempfile.TemporaryDirectory(prefix="citizen-extract-") as directory:
            path = Path(directory) / "upload.pdf"
            path.write_bytes(content)
            result = extract_pdf(path, document_id=uuid.uuid4().hex, ocr_workers=1, ocr_dpi=150, ocr_timeout=15)
            pages = [{"page": page.page_number, "text": page.text} for page in result.pages]
    else:
        from PIL import Image
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > 20_000_000:
                raise ValueError("Image exceeds the 20-megapixel limit")
            image.verify()
        pages = [{"page": 1, "text": ocr_png(content, timeout=15)}]
    remaining = MAX_TEXT
    truncated = False
    for page in pages:
        original = page["text"]
        page["text"] = original[:remaining]
        truncated |= len(original) > remaining
        remaining = max(0, remaining - len(page["text"]))
    return pages, truncated


@router.post("/extract")
async def extract_citizen_document(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    content_type = file.content_type or ""
    try:
        if content_type not in {"application/pdf", "image/png", "image/jpeg", "image/webp"}:
            raise HTTPException(415, "Choose a PDF, PNG, JPEG or WebP file")
        try:
            await user_rate_limiter.admit(str(user.id), "citizen_extract", limit=6)
        except RateLimitExceeded as exc:
            raise HTTPException(429, "Too many uploads. Try again shortly.", headers={"Retry-After": str(exc.retry_after_seconds)}) from exc
        content = await file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(413, "Files must be 10 MiB or smaller")
        if not content:
            raise HTTPException(422, "The file is empty")
        async with extraction_slots:
            pages, truncated = await asyncio.to_thread(extract_upload, content, content_type)
        if not any(page["text"].strip() for page in pages):
            raise HTTPException(422, "No readable text found. Try a clearer image or a text-based PDF.")
        return {"id": uuid.uuid4().hex, "filename": Path(file.filename or "Document").name[:180], "media_type": content_type, "pages": pages, "truncated": truncated}
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(422, "Document extraction failed. Try a clearer or smaller file.") from error
    finally:
        await file.close()
