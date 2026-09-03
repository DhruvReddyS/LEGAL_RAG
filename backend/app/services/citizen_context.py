"""Request-local document chunks; these never enter a shared vector collection."""
import json
import re

from app.schemas.chat import CitizenDocumentContext


def select_document_context(query: str, documents: list[CitizenDocumentContext]) -> str:
    terms = set(re.findall(r"\w{3,}", query.lower()))
    chunks = []
    for number, document in enumerate(documents, 1):
        for page in document.pages:
            words = page.text.split()
            for offset in range(0, len(words), 280):
                text = " ".join(words[offset:offset + 320])
                score = len(terms & set(re.findall(r"\w{3,}", text.lower())))
                chunks.append((score, {"document": f"D{number}", "filename": document.filename,
                                      "page": page.page, "text": text}))
    # Stable order breaks ties in document/page order. Bound model context, not retrieval settings.
    selected = []
    remaining = 9000
    for _, chunk in sorted(chunks, key=lambda item: -item[0]):
        if remaining <= 0:
            break
        chunk["text"] = chunk["text"][:remaining]
        remaining -= len(chunk["text"])
        selected.append(chunk)
    return json.dumps(selected, ensure_ascii=False) if selected else ""
