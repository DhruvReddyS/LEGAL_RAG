from __future__ import annotations

import hashlib
from pathlib import Path

from app.ingestion.metadata import CanonicalDocument


def sha256_file(path: Path, *, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def verify_document_checksum(document: CanonicalDocument, corpus_root: Path) -> None:
    path = corpus_root / document.local_path
    actual = sha256_file(path)
    if actual != document.sha256:
        raise ValueError(
            f"Checksum mismatch for {document.document_id}: expected {document.sha256}, got {actual}"
        )
