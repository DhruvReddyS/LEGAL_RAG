"""An officer uploading a damaged PDF was shown "FileDataError".

That is the extraction library's exception class. It tells the reader nothing
they can act on, and it publishes an implementation detail in a response.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.case_documents import _extract_pages


@pytest.mark.asyncio
async def test_a_damaged_pdf_is_described_in_words_not_an_exception_class() -> None:
    stored = SimpleNamespace(
        id=uuid.uuid4(), content_type="application/pdf", original_filename="damaged.pdf"
    )

    with pytest.raises(HTTPException) as refused:
        await _extract_pages(stored, b"%PDF-1.4\nthis is not really a pdf\x00\xff\xfe" * 40)

    assert refused.value.status_code == 422
    assert "could not be read" in refused.value.detail
    assert "Error" not in refused.value.detail
