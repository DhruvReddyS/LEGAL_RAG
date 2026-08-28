#!/usr/bin/env python3
"""Report durable embedding progress without touching the ingestion process.

Progress is measured in chunks, not documents.  A valid complete cache wins over
any leftover parts.  Otherwise, only the longest valid contiguous partial prefix
starting at chunk zero is counted, matching EmbeddingCache.load_prefix.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class Snapshot:
    measured_at: float
    total_documents: int
    total_chunks: int
    embedded_chunks: int
    remaining_chunks: int
    percent: float
    complete_cache_documents: int
    partial_cache_documents: int
    documents_without_embeddings: int
    invalid_complete_caches: int
    invalid_part_files: int


def _read_chunk_ids(path: Path) -> list[str]:
    ids: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                ids.append(str(json.loads(line)["chunk_id"]))
    return ids


def _read_gzip_json(path: Path) -> dict[str, Any] | None:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else None
    except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _embeddings_valid(value: Any, expected: int, dimension: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == expected
        and all(
            isinstance(item, dict)
            and isinstance(item.get("dense"), list)
            and len(item["dense"]) == dimension
            and isinstance(item.get("sparse"), dict)
            for item in value
        )
    )


def _complete_count(
    path: Path, chunk_ids: list[str], model: str, dimension: int
) -> tuple[int, bool]:
    if not path.exists():
        return 0, False
    payload = _read_gzip_json(path)
    valid = bool(
        payload
        and payload.get("model") == model
        and payload.get("chunk_ids") == chunk_ids
        and _embeddings_valid(payload.get("embeddings"), len(chunk_ids), dimension)
    )
    return (len(chunk_ids) if valid else 0), not valid


def _part_key(model: str, chunk_ids: list[str]) -> str:
    encoded = json.dumps(
        {"model": model, "chunk_ids": chunk_ids},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _partial_prefix_count(
    directory: Path, chunk_ids: list[str], model: str, dimension: int
) -> tuple[int, int]:
    if not directory.is_dir():
        return 0, 0
    candidates: dict[int, list[int]] = {}
    invalid = 0
    for path in directory.glob("*.json.gz"):
        payload = _read_gzip_json(path)
        try:
            start = int(payload["start"]) if payload else -1
            ids = [str(value) for value in payload["chunk_ids"]] if payload else []
            expected_name = f"{start:08d}-{_part_key(model, ids)}.json.gz"
            valid = bool(
                payload
                and payload.get("model") == model
                and start >= 0
                and ids
                and start + len(ids) <= len(chunk_ids)
                and path.name == expected_name
                and chunk_ids[start : start + len(ids)] == ids
                and _embeddings_valid(payload.get("embeddings"), len(ids), dimension)
            )
        except (KeyError, TypeError, ValueError):
            valid = False
            ids = []
            start = -1
        if valid:
            candidates.setdefault(start, []).append(len(ids))
        else:
            invalid += 1

    # Dynamic programming mirrors EmbeddingCache.load_prefix, but stores lengths.
    longest_at: dict[int, int] = {}
    for start in sorted(candidates, reverse=True):
        longest_at[start] = max(
            length + longest_at.get(start + length, 0)
            for length in candidates[start]
        )
    return longest_at.get(0, 0), invalid


def snapshot(root: Path, model: str, dimension: int) -> Snapshot:
    chunks_directory = root / "processed/chunks"
    cache_directory = root / "cache/embeddings"
    chunk_files = sorted(chunks_directory.glob("*.jsonl"))
    total_chunks = embedded = complete_docs = partial_docs = 0
    invalid_complete = invalid_parts = 0

    for chunks_path in chunk_files:
        canonical_id = chunks_path.stem
        chunk_ids = _read_chunk_ids(chunks_path)
        total_chunks += len(chunk_ids)
        complete, invalid = _complete_count(
            cache_directory / f"{canonical_id}.json.gz",
            chunk_ids,
            model,
            dimension,
        )
        invalid_complete += int(invalid)
        if complete:
            embedded += complete
            complete_docs += 1
            continue
        prefix, invalid = _partial_prefix_count(
            cache_directory / ".parts" / canonical_id,
            chunk_ids,
            model,
            dimension,
        )
        invalid_parts += invalid
        embedded += prefix
        partial_docs += int(prefix > 0)

    remaining = max(total_chunks - embedded, 0)
    return Snapshot(
        measured_at=time.time(),
        total_documents=len(chunk_files),
        total_chunks=total_chunks,
        embedded_chunks=embedded,
        remaining_chunks=remaining,
        percent=round(100 * embedded / total_chunks, 3) if total_chunks else 0.0,
        complete_cache_documents=complete_docs,
        partial_cache_documents=partial_docs,
        documents_without_embeddings=len(chunk_files) - complete_docs - partial_docs,
        invalid_complete_caches=invalid_complete,
        invalid_part_files=invalid_parts,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/legal_kb"))
    parser.add_argument("--model", default="BAAI/bge-m3")
    parser.add_argument("--dimension", type=int, default=1024)
    parser.add_argument(
        "--benchmark-seconds",
        type=int,
        default=0,
        help="take a second snapshot after this interval and report throughput",
    )
    args = parser.parse_args()
    first = snapshot(args.root, args.model, args.dimension)
    output: dict[str, Any] = {"snapshot": asdict(first)}
    if args.benchmark_seconds > 0:
        time.sleep(args.benchmark_seconds)
        second = snapshot(args.root, args.model, args.dimension)
        elapsed = second.measured_at - first.measured_at
        delta = second.embedded_chunks - first.embedded_chunks
        chunks_per_minute = 60 * delta / elapsed
        output = {
            "before": asdict(first),
            "after": asdict(second),
            "benchmark": {
                "elapsed_seconds": round(elapsed, 3),
                "new_embedded_chunks": delta,
                "chunks_per_minute": round(chunks_per_minute, 3),
                "estimated_minutes_remaining": (
                    round(second.remaining_chunks / chunks_per_minute, 2)
                    if chunks_per_minute > 0
                    else None
                ),
            },
        }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
