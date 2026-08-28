from __future__ import annotations

import gzip
import gc
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.core.config import settings
from app.ingestion.sparse import normalize_lexical_weights


@dataclass
class EmbeddedText:
    dense: list[float]
    sparse: dict[int, float]


def resolve_embedding_device() -> str:
    device = settings.embedding_device
    if device != "auto":
        return device
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except (ImportError, AttributeError):
        pass
    return "cpu"


class BGEM3Embedder:
    def __init__(self, model_name: str | None = None, *, use_fp16: bool | None = None) -> None:
        self.model_name = model_name or settings.embedding_model
        self.use_fp16 = use_fp16
        self._model: Any | None = None
        self._model_device: str | None = None

    def _clear_device_cache(self) -> None:
        try:
            import torch

            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
        except (ImportError, AttributeError):
            pass

    def _release_model(self) -> None:
        """Fully release the current model and reclaim MPS/GPU memory."""
        self._model = None
        self._model_device = None
        gc.collect()
        try:
            import torch

            if torch.backends.mps.is_available():
                torch.mps.synchronize()
                torch.mps.empty_cache()
        except (ImportError, AttributeError):
            pass

    def _load_model(self) -> Any:
        if self._model is None:
            from FlagEmbedding import BGEM3FlagModel

            device = resolve_embedding_device()
            self._model_device = device

            use_fp16 = self.use_fp16
            if use_fp16 is None:
                use_fp16 = device in {"cuda", "mps"}
            self._model = BGEM3FlagModel(
                self.model_name,
                use_fp16=use_fp16,
                devices=device,
            )
        return self._model

    def _encode_batch(self, batch: list[str], encode_options: dict[str, Any]) -> Any:
        """Encode a batch with IndexError retry and model rebuild for MPS."""
        model = self._load_model()
        try:
            return model.encode(batch, **encode_options)
        except IndexError:
            self._clear_device_cache()
            try:
                return model.encode(batch, **encode_options)
            except IndexError:
                if self._model_device != "mps":
                    raise
                self._release_model()
                model = self._load_model()
                return model.encode(batch, **encode_options)
        finally:
            self._clear_device_cache()

    @staticmethod
    def _parse_output(output: Any, expected: int) -> list[EmbeddedText]:
        batch_embeddings: list[EmbeddedText] = []
        for dense, sparse in zip(
            output["dense_vecs"], output["lexical_weights"], strict=True
        ):
            dense_list = [float(value) for value in dense]
            if len(dense_list) != settings.embedding_dimension:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {settings.embedding_dimension}, "
                    f"received {len(dense_list)}"
                )
            batch_embeddings.append(
                EmbeddedText(
                    dense=dense_list,
                    sparse=normalize_lexical_weights(sparse),
                )
            )
        if len(batch_embeddings) != expected:
            raise ValueError(
                f"Embedding count mismatch: expected {expected}, "
                f"received {len(batch_embeddings)}"
            )
        return batch_embeddings

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
        if batch_size < 1:
            raise ValueError("batch_size must be greater than zero")
        embedded: list[EmbeddedText] = []
        # Keep model calls bounded on every device. Besides preventing MPS from
        # retaining an entire long document, this provides a durable callback
        # boundary for crash-resumable ingestion.
        current_batch_size = batch_size
        batch_offset = 0
        while batch_offset < len(texts):
            batch = texts[batch_offset : batch_offset + current_batch_size]
            encode_options = {
                "batch_size": len(batch),
                "max_length": 8192,
                "return_dense": True,
                "return_sparse": True,
                "return_colbert_vecs": False,
            }
            try:
                output = self._encode_batch(batch, encode_options)
            except RuntimeError as exc:
                if "out of memory" not in str(exc):
                    raise
                # MPS OOM: release model, halve batch, rebuild, retry.
                import sys
                print(
                    json.dumps({
                        "event": "mps_oom_recovery",
                        "batch_offset": batch_offset,
                        "failed_batch_size": len(batch),
                        "current_batch_size": current_batch_size,
                    }),
                    file=sys.stderr,
                    flush=True,
                )
                self._release_model()
                if current_batch_size > 1:
                    current_batch_size = max(1, current_batch_size // 2)
                    self._load_model()
                    continue  # retry same offset with smaller batch
                # batch_size=1 still OOMs on MPS — fall back to CPU for this item
                if self._model_device == "mps" or self._model is None:
                    self._release_model()
                    from FlagEmbedding import BGEM3FlagModel

                    use_fp16 = self.use_fp16 if self.use_fp16 is not None else False
                    self._model = BGEM3FlagModel(
                        self.model_name,
                        use_fp16=use_fp16,
                        devices="cpu",
                    )
                    self._model_device = "cpu"
                    print(
                        json.dumps({
                            "event": "cpu_fallback",
                            "batch_offset": batch_offset,
                        }),
                        file=sys.stderr,
                        flush=True,
                    )
                    continue  # retry same offset on CPU
                raise  # already on CPU and still OOM — nothing more to try
            batch_embeddings = self._parse_output(output, len(batch))
            embedded.extend(batch_embeddings)
            if on_batch is not None:
                on_batch(start_index + batch_offset, batch_embeddings)
            batch_offset += len(batch)
            # After a successful batch, try to restore batch size toward the
            # original if it was reduced during OOM recovery.
            if current_batch_size < batch_size:
                current_batch_size = min(batch_size, current_batch_size * 2)
        # If we fell back to CPU, restore MPS for the next document.
        if self._model_device == "cpu" and resolve_embedding_device() == "mps":
            self._release_model()
        return embedded


class EmbeddingCache:
    """Atomic complete caches plus resumable per-batch document checkpoints."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, canonical_document_id: str) -> Path:
        return self.directory / f"{canonical_document_id}.json.gz"

    def _parts_directory(self, canonical_document_id: str) -> Path:
        return self.directory / ".parts" / canonical_document_id

    @staticmethod
    def _part_key(model_name: str, chunk_ids: list[str]) -> str:
        encoded = json.dumps(
            {"model": model_name, "chunk_ids": chunk_ids},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _part_path(
        self,
        canonical_document_id: str,
        start: int,
        model_name: str,
        chunk_ids: list[str],
    ) -> Path:
        key = self._part_key(model_name, chunk_ids)
        return self._parts_directory(canonical_document_id) / f"{start:08d}-{key}.json.gz"

    @staticmethod
    def _deserialize_embeddings(payload: list[dict[str, Any]]) -> list[EmbeddedText]:
        return [
            EmbeddedText(
                dense=[float(value) for value in item["dense"]],
                sparse={int(key): float(value) for key, value in item["sparse"].items()},
            )
            for item in payload
        ]

    def load(self, canonical_document_id: str, chunk_ids: list[str]) -> list[EmbeddedText] | None:
        path = self._path(canonical_document_id)
        if not path.exists():
            return None
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("model") != settings.embedding_model or payload.get("chunk_ids") != chunk_ids:
            return None
        embeddings = self._deserialize_embeddings(payload["embeddings"])
        return embeddings if len(embeddings) == len(chunk_ids) else None

    def load_prefix(
        self,
        canonical_document_id: str,
        chunk_ids: list[str],
        *,
        model_name: str | None = None,
    ) -> list[EmbeddedText]:
        """Load the longest valid contiguous prefix of saved embedding batches."""
        model = model_name or settings.embedding_model
        parts_directory = self._parts_directory(canonical_document_id)
        if not parts_directory.exists():
            return []

        candidates: dict[int, list[tuple[list[str], list[EmbeddedText]]]] = {}
        for path in parts_directory.glob("*.json.gz"):
            try:
                with gzip.open(path, "rt", encoding="utf-8") as handle:
                    payload = json.load(handle)
                start = int(payload["start"])
                part_chunk_ids = [str(value) for value in payload["chunk_ids"]]
                if (
                    payload.get("model") != model
                    or start < 0
                    or not part_chunk_ids
                    or start + len(part_chunk_ids) > len(chunk_ids)
                    or path != self._part_path(
                        canonical_document_id, start, model, part_chunk_ids
                    )
                    or chunk_ids[start : start + len(part_chunk_ids)] != part_chunk_ids
                ):
                    continue
                embeddings = self._deserialize_embeddings(payload["embeddings"])
                if len(embeddings) != len(part_chunk_ids) or any(
                    len(item.dense) != settings.embedding_dimension for item in embeddings
                ):
                    continue
                candidates.setdefault(start, []).append((part_chunk_ids, embeddings))
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue

        longest_at: dict[int, list[EmbeddedText]] = {}
        for cursor in sorted(candidates, reverse=True):
            best: list[EmbeddedText] = []
            for part_chunk_ids, embeddings in candidates[cursor]:
                combined = [
                    *embeddings,
                    *longest_at.get(cursor + len(part_chunk_ids), []),
                ]
                if len(combined) > len(best):
                    best = combined
            longest_at[cursor] = best
        return longest_at.get(0, [])

    def save_part(
        self,
        canonical_document_id: str,
        start: int,
        chunk_ids: list[str],
        embeddings: list[EmbeddedText],
        *,
        model_name: str | None = None,
    ) -> None:
        if start < 0:
            raise ValueError("start must not be negative")
        if not chunk_ids or len(chunk_ids) != len(embeddings):
            raise ValueError("Part chunk and embedding counts must be equal and non-zero")
        model = model_name or settings.embedding_model
        path = self._part_path(canonical_document_id, start, model, chunk_ids)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        payload = {
            "model": model,
            "start": start,
            "chunk_ids": chunk_ids,
            "embeddings": [
                {"dense": item.dense, "sparse": item.sparse} for item in embeddings
            ],
        }
        with gzip.open(temporary, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
        os.replace(temporary, path)

    def cleanup_parts(self, canonical_document_id: str) -> None:
        parts_directory = self._parts_directory(canonical_document_id)
        if not parts_directory.exists():
            return
        for path in parts_directory.iterdir():
            if path.is_file():
                path.unlink()
        try:
            parts_directory.rmdir()
            parts_directory.parent.rmdir()
        except OSError:
            pass

    def save(
        self,
        canonical_document_id: str,
        chunk_ids: list[str],
        embeddings: list[EmbeddedText],
    ) -> None:
        if len(chunk_ids) != len(embeddings):
            raise ValueError("Complete cache chunk and embedding counts must match")
        path = self._path(canonical_document_id)
        temporary = path.with_suffix(path.suffix + ".tmp")
        payload = {
            "model": settings.embedding_model,
            "chunk_ids": chunk_ids,
            "embeddings": [
                {"dense": item.dense, "sparse": item.sparse}
                for item in embeddings
            ],
        }
        with gzip.open(temporary, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
        os.replace(temporary, path)
        self.cleanup_parts(canonical_document_id)
