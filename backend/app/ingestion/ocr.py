from __future__ import annotations

import io


def ocr_png(png_bytes: bytes, *, language: str = "eng") -> str:
    """Run Tesseract on a rendered page; imports stay lazy for API startup speed."""
    import pytesseract
    from PIL import Image

    with Image.open(io.BytesIO(png_bytes)) as image:
        return pytesseract.image_to_string(image, lang=language, config="--psm 6")
