from __future__ import annotations

import argparse
import asyncio
import json
import math
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from qdrant_client import models

from app.core.config import settings
from app.core.qdrant import create_qdrant_client
from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS
from app.ingestion.metadata import iter_canonical_documents, load_manifest


REQUIRED_GOLD_PAYLOAD_FIELDS = frozenset(
    {
        "chunk_id",
        "text",
        "source_type",
        "title",
        "act_name",
        "section",
        "jurisdiction",
        "court",
        "decision_year",
        "is_current",
        "source_id",
        "document_id",
        "canonical_document_id",
        "page_start",
        "page_end",
        "heading_path",
        "verified_official",
        "quality_status",
        "corpus_tier",
    }
)
MAX_REPORTED_ISSUES = 100


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def _finite_numbers(values: object) -> bool:
    return isinstance(values, list) and bool(values) and all(
        isinstance(value, (int, float)) and math.isfinite(value) for value in values
    )


def _vector_issues(vector: object) -> list[str]:
    if not isinstance(vector, dict):
        return ["named vectors are missing"]
    issues: list[str] = []
    dense = vector.get(settings.qdrant_dense_vector_name)
    if not _finite_numbers(dense):
        issues.append("dense vector is missing, empty, or non-finite")
    elif len(dense) != settings.embedding_dimension:
        issues.append(
            f"dense dimension is {len(dense)}, expected {settings.embedding_dimension}"
        )

    sparse = vector.get(settings.qdrant_sparse_vector_name)
    if isinstance(sparse, models.SparseVector):
        indices, values = sparse.indices, sparse.values
    elif isinstance(sparse, dict):
        indices, values = sparse.get("indices"), sparse.get("values")
    else:
        indices = values = None
    if not isinstance(indices, list) or not indices:
        issues.append("sparse indices are missing or empty")
    elif not all(isinstance(index, int) and index >= 0 for index in indices):
        issues.append("sparse indices contain an invalid token id")
    elif len(indices) != len(set(indices)):
        issues.append("sparse indices contain duplicates")
    if not _finite_numbers(values):
        issues.append("sparse values are missing, empty, or non-finite")
    elif isinstance(indices, list) and len(indices) != len(values):
        issues.append("sparse index/value counts differ")
    return issues


def _point_issues(point: Any) -> list[str]:
    payload = dict(point.payload or {})
    issues: list[str] = []
    missing = sorted(REQUIRED_GOLD_PAYLOAD_FIELDS - payload.keys())
    if missing:
        issues.append(f"missing payload fields: {', '.join(missing)}")
    if payload.get("corpus_tier") != "gold":
        issues.append("corpus_tier is not gold")
    if payload.get("verified_official") is not True:
        issues.append("verified_official is not true")
    # Qdrant omits null payload values. A decision date is therefore optional
    # for statutes, guidance, and records whose source metadata has no date.
    # When present, it must be a non-blank ISO-like value.
    if "decision_date" in payload and not str(payload["decision_date"] or "").strip():
        issues.append("decision_date is blank")
    if not str(payload.get("text") or "").strip():
        issues.append("text is empty")
    if not str(payload.get("chunk_id") or "").strip():
        issues.append("chunk_id is empty")
    else:
        expected_id = _expected_point_id(str(payload["chunk_id"]))
        if str(point.id) != expected_id:
            issues.append(f"point id does not match stable chunk id ({expected_id})")
    page_start, page_end = payload.get("page_start"), payload.get("page_end")
    if not isinstance(page_start, int) or not isinstance(page_end, int) or not (
        1 <= page_start <= page_end
    ):
        issues.append("page range is invalid")
    issues.extend(_vector_issues(point.vector))
    return issues


async def _scroll_gold_points(client: Any) -> list[Any]:
    points: list[Any] = []
    offset: Any | None = None
    gold_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="corpus_tier",
                match=models.MatchValue(value="gold"),
            )
        ]
    )
    while True:
        page, offset = await client.scroll(
            collection_name=GLOBAL_LEGAL_CORPUS,
            scroll_filter=gold_filter,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        points.extend(page)
        if offset is None:
            return points


def _load_expected_chunks(
    root: Path,
    canonical_ids: set[str],
) -> tuple[dict[str, dict[str, dict[str, Any]]], Counter[str], list[str]]:
    expected: dict[str, dict[str, dict[str, Any]]] = {}
    source_counts: Counter[str] = Counter()
    issues: list[str] = []
    chunks_dir = root / "processed/chunks"
    disk_ids = {path.stem for path in chunks_dir.glob("*.jsonl")}
    for canonical_id in sorted(disk_ids - canonical_ids):
        issues.append(f"orphan chunk file: {canonical_id}.jsonl")
    for canonical_id in sorted(canonical_ids):
        path = chunks_dir / f"{canonical_id}.jsonl"
        if not path.exists():
            issues.append(f"missing chunk file: {canonical_id}.jsonl")
            expected[canonical_id] = {}
            continue
        document_chunks: dict[str, dict[str, Any]] = {}
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as exc:
                issues.append(f"invalid JSON in {path.name}:{line_number}: {exc}")
                continue
            chunk_id = str(chunk.get("chunk_id") or "")
            if not chunk_id:
                issues.append(f"missing chunk_id in {path.name}:{line_number}")
                continue
            if chunk_id in document_chunks:
                issues.append(f"duplicate chunk_id on disk: {chunk_id}")
            if chunk.get("canonical_document_id") != canonical_id:
                issues.append(
                    f"chunk {chunk_id} belongs to {chunk.get('canonical_document_id')}, "
                    f"not file {canonical_id}"
                )
            document_chunks[chunk_id] = chunk
            source_counts[str(chunk.get("source_type") or "unknown")] += 1
        if not document_chunks:
            issues.append(f"no chunks in {path.name}")
        expected[canonical_id] = document_chunks
    return expected, source_counts, issues


async def build_ingestion_report(
    *,
    corpus_root: Path | None = None,
    require_complete: bool = False,
    client: Any | None = None,
) -> dict[str, Any]:
    root = corpus_root or Path(settings.legal_kb_root)
    manifest = load_manifest(root / "metadata/canonical_documents.jsonl")
    canonical = list(iter_canonical_documents(manifest))
    canonical_by_id = {item.canonical_document_id: item for item in canonical}
    canonical_ids = set(canonical_by_id)
    checkpoint_path = root / "logs/ingestion_checkpoint.json"
    checkpoint = (
        _load_json(checkpoint_path)
        if checkpoint_path.exists()
        else {"completed": {}, "failed": {}}
    )

    expected, chunk_counts, issues = _load_expected_chunks(root, canonical_ids)
    total_chunks = sum(len(chunks) for chunks in expected.values())

    completed_entries = checkpoint.get("completed", {})
    completed_ids = set(completed_entries)
    for canonical_id in sorted(canonical_ids - completed_ids):
        issues.append(f"checkpoint missing completed document: {canonical_id}")
    for canonical_id in sorted(completed_ids - canonical_ids):
        issues.append(f"orphan completed checkpoint: {canonical_id}")
    for canonical_id in sorted(canonical_ids & completed_ids):
        entry = completed_entries[canonical_id]
        document = canonical_by_id[canonical_id]
        if entry.get("sha256") != document.sha256:
            issues.append(f"checkpoint SHA mismatch: {canonical_id}")
        if entry.get("chunk_count") != len(expected.get(canonical_id, {})):
            issues.append(f"checkpoint chunk count mismatch: {canonical_id}")

    ocr_pages = 0
    ocr_documents = 0
    extraction_warnings = 0
    extracted_dir = root / "processed/extracted_text"
    extracted_ids = {path.stem for path in extracted_dir.glob("*.json")}
    for canonical_id in sorted(extracted_ids - canonical_ids):
        issues.append(f"orphan extracted-text file: {canonical_id}.json")
    for canonical_id in sorted(canonical_ids - extracted_ids):
        issues.append(f"missing extracted-text file: {canonical_id}.json")
    for canonical_id in sorted(canonical_ids & extracted_ids):
        extracted = _load_json(extracted_dir / f"{canonical_id}.json")
        document_ocr_pages = sum(bool(page["ocr_used"]) for page in extracted["pages"])
        ocr_pages += document_ocr_pages
        ocr_documents += document_ocr_pages > 0
        extraction_warnings += len(extracted.get("warnings", []))

    owns_client = client is None
    qdrant = client or create_qdrant_client()
    try:
        collection = await qdrant.get_collection(GLOBAL_LEGAL_CORPUS)
        collection_points = collection.points_count or 0
        gold_points = await _scroll_gold_points(qdrant)
    finally:
        if owns_client:
            await qdrant.close()

    actual: dict[str, set[str]] = defaultdict(set)
    seen_chunk_ids: set[str] = set()
    point_issue_count = 0
    for point in gold_points:
        payload = dict(point.payload or {})
        canonical_id = str(payload.get("canonical_document_id") or "")
        chunk_id = str(payload.get("chunk_id") or "")
        if canonical_id not in canonical_ids:
            issues.append(f"orphan Gold point {point.id}: canonical={canonical_id or '<missing>'}")
        if chunk_id in seen_chunk_ids:
            issues.append(f"duplicate Gold chunk_id: {chunk_id}")
        seen_chunk_ids.add(chunk_id)
        actual[canonical_id].add(chunk_id)
        for issue in _point_issues(point):
            point_issue_count += 1
            issues.append(f"Gold point {point.id}: {issue}")

    for canonical_id in sorted(canonical_ids):
        expected_ids = set(expected.get(canonical_id, {}))
        actual_ids = actual.get(canonical_id, set())
        missing_ids = expected_ids - actual_ids
        orphan_ids = actual_ids - expected_ids
        if missing_ids:
            issues.append(
                f"{canonical_id}: {len(missing_ids)} missing Qdrant chunks "
                f"(sample: {', '.join(sorted(missing_ids)[:3])})"
            )
        if orphan_ids:
            issues.append(
                f"{canonical_id}: {len(orphan_ids)} orphan Qdrant chunks "
                f"(sample: {', '.join(sorted(orphan_ids)[:3])})"
            )

    failures = checkpoint.get("failed", {})
    completed = len(completed_ids & canonical_ids)
    report = {
        "physical_documents": len(manifest),
        "canonical_documents": len(canonical),
        "completed_documents": completed,
        "failed_documents": len(failures),
        "extraction_failures": failures,
        "ocr_documents": ocr_documents,
        "ocr_pages": ocr_pages,
        "extraction_warnings": extraction_warnings,
        "total_chunks_on_disk": total_chunks,
        "qdrant_points": collection_points,
        "qdrant_gold_points": len(gold_points),
        "point_payload_vector_issues": point_issue_count,
        "validation_issue_count": len(issues),
        "validation_issues": issues[:MAX_REPORTED_ISSUES],
        "average_chunks_per_document_type": {
            source_type: round(
                count
                / max(
                    1,
                    sum(doc.resolved_type().value == source_type for doc in canonical),
                ),
                2,
            )
            for source_type, count in sorted(chunk_counts.items())
        },
    }
    lines = [
        "# Gold Corpus Ingestion Report",
        "",
        f"- Physical documents: {report['physical_documents']}",
        f"- Canonical documents: {report['canonical_documents']}",
        f"- Successfully ingested canonical documents: {completed}",
        f"- Failed documents: {len(failures)}",
        f"- Documents requiring OCR: {ocr_documents}",
        f"- OCR-processed pages: {ocr_pages}",
        f"- Extraction warnings: {extraction_warnings}",
        f"- Chunks on disk: {total_chunks}",
        f"- Qdrant points (all tiers): {collection_points}",
        f"- Qdrant Gold points: {len(gold_points)}",
        f"- Payload/vector issues: {point_issue_count}",
        f"- Validation issues: {len(issues)}",
        "",
        "## Average chunks per source type",
        "",
    ]
    lines.extend(
        f"- `{source_type}`: {average}"
        for source_type, average in report["average_chunks_per_document_type"].items()
    )
    lines.extend(["", "## Failures", ""])
    if failures:
        lines.extend(
            f"- `{canonical_id}`: {failure['error']}"
            for canonical_id, failure in sorted(failures.items())
        )
    else:
        lines.append("No ingestion failures recorded.")
    lines.extend(["", "## Integrity validation", ""])
    if issues:
        lines.extend(f"- {issue}" for issue in issues[:MAX_REPORTED_ISSUES])
        if len(issues) > MAX_REPORTED_ISSUES:
            lines.append(f"- … {len(issues) - MAX_REPORTED_ISSUES} additional issues omitted")
    else:
        lines.append("All per-document chunks, payloads, and vectors passed validation.")
    (root / "logs/ingestion_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    if require_complete and (
        completed != len(canonical)
        or failures
        or len(gold_points) != total_chunks
        or issues
    ):
        raise RuntimeError(
            "Gold ingestion validation failed: "
            f"completed={completed}/{len(canonical)}, failures={len(failures)}, "
            f"Gold points={len(gold_points)}/{total_chunks}, issues={len(issues)}"
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Gold corpus ingestion")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(build_ingestion_report(require_complete=args.require_complete)),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
