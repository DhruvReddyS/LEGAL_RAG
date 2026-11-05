"""Never embed the same text twice.

A rebuild spends nearly all its hours embedding, and most chunks come out of a
parser fix with the same text they went in with. The per-document cache cannot
help: chunk ids change and a re-chunk has to discard it. So this keys a vector on
what produced it, the model and the exact text, which stays true across rebuilds,
documents and collections. An interrupted run also keeps every batch it finished.

SQLite because a corpus is a few hundred thousand small rows, one process writes
during ingestion, and a single file is easy to delete: doing so only costs time.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from array import array
from pathlib import Path
from typing import Any, Callable

from app.ingestion.embedder import EmbeddedText

_READ_BATCH = 500


def content_key(model_name: str, text: str) -> str:
    return hashlib.sha256(f"{model_name}\0{text}".encode("utf-8")).hexdigest()


class ContentEmbeddingStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS embeddings "
                "(key TEXT PRIMARY KEY, dense BLOB NOT NULL, sparse TEXT NOT NULL) WITHOUT ROWID"
            )

    def _connect(self) -> sqlite3.Connection:
        # One per call: ingestion embeds on a worker thread.
        return sqlite3.connect(self.path, timeout=30)

    def get_many(self, keys: list[str]) -> dict[str, EmbeddedText]:
        found: dict[str, EmbeddedText] = {}
        with self._connect() as connection:
            for start in range(0, len(keys), _READ_BATCH):
                part = keys[start : start + _READ_BATCH]
                marks = ",".join("?" * len(part))
                rows = connection.execute(
                    f"SELECT key, dense, sparse FROM embeddings WHERE key IN ({marks})", part
                )
                for key, dense, sparse in rows:
                    found[key] = EmbeddedText(
                        dense=array("f", dense).tolist(),
                        sparse={int(token): float(weight) for token, weight in json.loads(sparse).items()},
                    )
        return found

    def put_many(self, items: list[tuple[str, EmbeddedText]]) -> None:
        with self._connect() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO embeddings (key, dense, sparse) VALUES (?, ?, ?)",
                [
                    (key, array("f", embedded.dense).tobytes(), json.dumps(embedded.sparse))
                    for key, embedded in items
                ],
            )


class ReusingEmbedder:
    """An embedder that only asks the model about text it has not seen."""

    def __init__(self, embedder: Any, store: ContentEmbeddingStore) -> None:
        self._embedder = embedder
        self._store = store
        self.reused = 0
        self.embedded = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._embedder, name)

    def embed_texts(
        self,
        texts: list[str],
        *,
        batch_size: int = 8,
        on_batch: Callable[[int, list[EmbeddedText]], None] | None = None,
        start_index: int = 0,
    ) -> list[EmbeddedText]:
        if not texts:
            return []
        keys = [content_key(self._embedder.model_name, text) for text in texts]
        known = self._store.get_many(list(set(keys)))
        # Repeats within a document are embedded once as well.
        missing = list(dict.fromkeys(key for key in keys if key not in known))
        text_of = dict(zip(keys, texts))

        def keep(start: int, batch: list[EmbeddedText]) -> None:
            # Stored as each batch finishes, so a crash loses at most one batch.
            self._store.put_many(list(zip(missing[start : start + len(batch)], batch)))

        if missing:
            fresh = self._embedder.embed_texts(
                [text_of[key] for key in missing], batch_size=batch_size, on_batch=keep
            )
            known.update(zip(missing, fresh))
        self.embedded += len(missing)
        self.reused += len(keys) - len(missing)

        embeddings = [known[key] for key in keys]
        if on_batch is not None:
            on_batch(start_index, embeddings)
        return embeddings
