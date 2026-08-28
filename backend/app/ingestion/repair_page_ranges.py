from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import unicodedata
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from qdrant_client import AsyncQdrantClient

from app.core.qdrant import create_qdrant_client
from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS


_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def normalized_tokens(text: str) -> list[str]:
    """Return alignment tokens resilient to harmless PDF text-format differences."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("\u00ad", "")
    return _TOKEN.findall(normalized)


@dataclass(frozen=True)
class PageAlignment:
    status: str
    page_start: int | None = None
    page_end: int | None = None
    candidate_ranges: tuple[tuple[int, int], ...] = ()
    reason: str | None = None


class PageTokenIndex:
    """Token-level index retaining the extracted page provenance of every token."""

    def __init__(self, pages: Iterable[dict[str, Any]]) -> None:
        self.tokens: list[str] = []
        self.pages: list[int] = []
        self.positions: dict[str, list[int]] = defaultdict(list)
        for page in pages:
            page_number = int(page["page_number"])
            for token in normalized_tokens(str(page.get("text", ""))):
                self.positions[token].append(len(self.tokens))
                self.tokens.append(token)
                self.pages.append(page_number)

    def align(self, chunk_text: str) -> PageAlignment:
        needle = normalized_tokens(chunk_text)
        if not needle:
            return PageAlignment(status="unmatched", reason="chunk has no alignable tokens")
        if len(needle) > len(self.tokens):
            return PageAlignment(status="unmatched", reason="chunk is longer than extracted text")

        # Select the rarest token as the anchor. This keeps exact matching fast for
        # large judgments without weakening the evidence needed for a page citation.
        anchor_offset = min(
            range(len(needle)),
            key=lambda offset: len(self.positions.get(needle[offset], ())),
        )
        anchor_positions = self.positions.get(needle[anchor_offset], ())
        ranges: set[tuple[int, int]] = set()
        for anchor_position in anchor_positions:
            start = anchor_position - anchor_offset
            end = start + len(needle)
            if start < 0 or end > len(self.tokens):
                continue
            if self.tokens[start:end] == needle:
                ranges.add((self.pages[start], self.pages[end - 1]))

        ordered = tuple(sorted(ranges))
        if not ordered:
            return PageAlignment(
                status="unmatched",
                reason="normalized token sequence was not found in extracted pages",
            )
        if len(ordered) > 1:
            return PageAlignment(
                status="ambiguous",
                candidate_ranges=ordered,
                reason="the same normalized token sequence occurs on multiple page ranges",
            )
        page_start, page_end = ordered[0]
        return PageAlignment(
            status="matched",
            page_start=page_start,
            page_end=page_end,
            candidate_ranges=ordered,
        )


@dataclass(frozen=True)
class ChunkRepair:
    chunk_id: str
    old_page_start: int
    old_page_end: int
    new_page_start: int
    new_page_end: int


@dataclass
class DocumentRepair:
    canonical_document_id: str
    chunks_path: Path
    original_chunks: list[dict[str, Any]]
    repaired_chunks: list[dict[str, Any]]
    changes: list[ChunkRepair] = field(default_factory=list)
    unmatched: list[dict[str, Any]] = field(default_factory=list)
    ambiguous: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RepairReport:
    mode: str
    documents_scanned: int = 0
    chunks_scanned: int = 0
    chunks_changed: int = 0
    chunks_unchanged: int = 0
    unmatched_chunks: int = 0
    ambiguous_chunks: int = 0
    local_files_written: int = 0
    qdrant_payloads_updated: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "documents_scanned": self.documents_scanned,
            "chunks_scanned": self.chunks_scanned,
            "chunks_changed": self.chunks_changed,
            "chunks_unchanged": self.chunks_unchanged,
            "unmatched_chunks": self.unmatched_chunks,
            "ambiguous_chunks": self.ambiguous_chunks,
            "local_files_written": self.local_files_written,
            "qdrant_payloads_updated": self.qdrant_payloads_updated,
            "details": self.details,
        }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def plan_document_repair(extracted_path: Path, chunks_path: Path) -> DocumentRepair:
    extracted = json.loads(extracted_path.read_text(encoding="utf-8"))
    original_chunks = _read_jsonl(chunks_path)
    index = PageTokenIndex(extracted.get("pages", []))
    repaired_chunks: list[dict[str, Any]] = []
    repair = DocumentRepair(
        canonical_document_id=chunks_path.stem,
        chunks_path=chunks_path,
        original_chunks=original_chunks,
        repaired_chunks=repaired_chunks,
    )

    for chunk in original_chunks:
        repaired = dict(chunk)
        alignment = index.align(str(chunk.get("text", "")))
        if alignment.status == "matched":
            assert alignment.page_start is not None and alignment.page_end is not None
            old_start = int(chunk["page_start"])
            old_end = int(chunk["page_end"])
            if (old_start, old_end) != (alignment.page_start, alignment.page_end):
                repaired["page_start"] = alignment.page_start
                repaired["page_end"] = alignment.page_end
                repair.changes.append(
                    ChunkRepair(
                        chunk_id=str(chunk["chunk_id"]),
                        old_page_start=old_start,
                        old_page_end=old_end,
                        new_page_start=alignment.page_start,
                        new_page_end=alignment.page_end,
                    )
                )
        elif alignment.status == "ambiguous":
            repair.ambiguous.append(
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "candidate_ranges": [list(item) for item in alignment.candidate_ranges],
                    "reason": alignment.reason,
                }
            )
        else:
            repair.unmatched.append(
                {"chunk_id": chunk.get("chunk_id"), "reason": alignment.reason}
            )
        repaired_chunks.append(repaired)

    # Page repair must never alter stable identity, retrieval content, or metadata.
    for original, repaired in zip(original_chunks, repaired_chunks, strict=True):
        for key, value in original.items():
            if key not in {"page_start", "page_end"} and repaired.get(key) != value:
                raise AssertionError(f"repair unexpectedly changed {key!r}")
    return repair


def build_repair_plan(
    corpus_root: Path,
    *,
    document_id: str | None = None,
    limit: int | None = None,
) -> list[DocumentRepair]:
    chunks_dir = corpus_root / "processed/chunks"
    extracted_dir = corpus_root / "processed/extracted_text"
    plans: list[DocumentRepair] = []
    for chunks_path in sorted(chunks_dir.glob("*.jsonl")):
        if document_id and document_id not in {chunks_path.stem, chunks_path.name}:
            continue
        extracted_path = extracted_dir / f"{chunks_path.stem}.json"
        if not extracted_path.exists():
            raise FileNotFoundError(f"Missing extracted document: {extracted_path}")
        plans.append(plan_document_repair(extracted_path, chunks_path))
        if limit is not None and len(plans) >= limit:
            break
    return plans


def _atomic_write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".page-range-repair.tmp")
    temporary.write_text(
        "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def apply_local_repairs(plans: Iterable[DocumentRepair]) -> int:
    written = 0
    for plan in plans:
        if not plan.changes:
            continue
        _atomic_write_jsonl(plan.chunks_path, plan.repaired_chunks)
        written += 1
    return written


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


async def update_qdrant_page_payloads(
    plans: Iterable[DocumentRepair],
    client: AsyncQdrantClient,
) -> int:
    """Update only citation payload fields; vectors and all other payload stay intact."""
    grouped: dict[tuple[int, int], list[str]] = defaultdict(list)
    for plan in plans:
        for change in plan.changes:
            grouped[(change.new_page_start, change.new_page_end)].append(
                _point_id(change.chunk_id)
            )
    updated = 0
    for (page_start, page_end), point_ids in grouped.items():
        await client.set_payload(
            collection_name=GLOBAL_LEGAL_CORPUS,
            payload={"page_start": page_start, "page_end": page_end},
            points=point_ids,
            wait=True,
        )
        updated += len(point_ids)
    return updated


def summarize(plans: list[DocumentRepair], *, mode: str) -> RepairReport:
    report = RepairReport(mode=mode, documents_scanned=len(plans))
    for plan in plans:
        chunk_count = len(plan.original_chunks)
        report.chunks_scanned += chunk_count
        report.chunks_changed += len(plan.changes)
        report.unmatched_chunks += len(plan.unmatched)
        report.ambiguous_chunks += len(plan.ambiguous)
        report.chunks_unchanged += (
            chunk_count - len(plan.changes) - len(plan.unmatched) - len(plan.ambiguous)
        )
        if plan.changes or plan.unmatched or plan.ambiguous:
            report.details.append(
                {
                    "canonical_document_id": plan.canonical_document_id,
                    "changes": [change.__dict__ for change in plan.changes],
                    "unmatched": plan.unmatched,
                    "ambiguous": plan.ambiguous,
                }
            )
    return report


async def run(args: argparse.Namespace) -> RepairReport:
    if args.update_qdrant and not args.apply:
        raise ValueError("--update-qdrant requires --apply so local repair happens first")
    plans = build_repair_plan(
        args.corpus_root,
        document_id=args.document_id,
        limit=args.limit,
    )
    report = summarize(plans, mode="apply" if args.apply else "dry-run")
    if args.apply:
        report.local_files_written = apply_local_repairs(plans)
        if args.update_qdrant:
            client = create_qdrant_client()
            try:
                report.qdrant_payloads_updated = await update_qdrant_page_payloads(plans, client)
            finally:
                await client.close()
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Conservatively repair chunk page ranges from extracted per-page text."
    )
    parser.add_argument("corpus_root", type=Path)
    parser.add_argument("--document-id")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Atomically write local chunk repairs (default is dry-run).",
    )
    parser.add_argument(
        "--update-qdrant",
        action="store_true",
        help="After local apply succeeds, update only Qdrant page payloads.",
    )
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = asyncio.run(run(args)).as_dict()
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
