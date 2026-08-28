from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ingestion.repair_page_ranges import (
    PageTokenIndex,
    apply_local_repairs,
    build_repair_plan,
    run,
    summarize,
    update_qdrant_page_payloads,
)


def _write_fixture(root: Path, pages: list[str], chunks: list[dict[str, object]]) -> Path:
    extracted = root / "processed/extracted_text/gold-canonical-test.json"
    chunk_path = root / "processed/chunks/gold-canonical-test.jsonl"
    extracted.parent.mkdir(parents=True)
    chunk_path.parent.mkdir(parents=True)
    extracted.write_text(
        json.dumps(
            {
                "document_id": "gold-doc-test",
                "pages": [
                    {"page_number": number, "text": text}
                    for number, text in enumerate(pages, start=1)
                ],
            }
        ),
        encoding="utf-8",
    )
    chunk_path.write_text(
        "".join(json.dumps(chunk) + "\n" for chunk in chunks),
        encoding="utf-8",
    )
    return chunk_path


def _chunk(chunk_id: str, text: str, start: int = 1, end: int = 9) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document_id": "gold-doc-test",
        "canonical_document_id": "gold-canonical-test",
        "text": text,
        "page_start": start,
        "page_end": end,
        "metadata_that_must_survive": {"nested": [1, 2, 3]},
    }


def test_normalized_alignment_finds_tight_cross_page_range() -> None:
    index = PageTokenIndex(
        [
            {"page_number": 4, "text": "irrelevant preface"},
            {"page_number": 5, "text": "The Court’s finding—begins here"},
            {"page_number": 6, "text": "and concludes THERE."},
        ]
    )

    result = index.align("the court's finding begins here AND concludes there")

    assert result.status == "matched"
    assert (result.page_start, result.page_end) == (5, 6)


def test_ambiguous_and_unmatched_chunks_are_not_changed(tmp_path: Path) -> None:
    _write_fixture(
        tmp_path,
        ["Repeated heading", "middle", "Repeated heading"],
        [
            _chunk("ambiguous", "repeated heading", 1, 3),
            _chunk("missing", "words not present", 2, 2),
        ],
    )

    plan = build_repair_plan(tmp_path)[0]

    assert plan.changes == []
    assert plan.ambiguous[0]["chunk_id"] == "ambiguous"
    assert plan.ambiguous[0]["candidate_ranges"] == [[1, 1], [3, 3]]
    assert plan.unmatched[0]["chunk_id"] == "missing"
    assert plan.repaired_chunks == plan.original_chunks


def test_dry_run_reports_without_writing(tmp_path: Path) -> None:
    chunk_path = _write_fixture(
        tmp_path,
        ["cover", "unique operative words", "appendix"],
        [_chunk("repair-me", "UNIQUE operative words")],
    )
    before = chunk_path.read_bytes()

    plans = build_repair_plan(tmp_path)
    report = summarize(plans, mode="dry-run")

    assert report.chunks_changed == 1
    assert report.local_files_written == 0
    assert chunk_path.read_bytes() == before


def test_apply_changes_only_pages_and_leaves_embedding_cache_untouched(tmp_path: Path) -> None:
    chunk_path = _write_fixture(
        tmp_path,
        ["cover", "unique operative words", "appendix"],
        [_chunk("stable-id", "unique operative words")],
    )
    cache = tmp_path / "cache/embeddings/gold-canonical-test.json.gz"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"opaque-embedding-cache")
    cache_before = cache.read_bytes()

    plans = build_repair_plan(tmp_path)
    assert apply_local_repairs(plans) == 1

    repaired = json.loads(chunk_path.read_text(encoding="utf-8"))
    assert repaired["page_start"] == 2
    assert repaired["page_end"] == 2
    assert repaired["chunk_id"] == "stable-id"
    assert repaired["text"] == "unique operative words"
    assert repaired["metadata_that_must_survive"] == {"nested": [1, 2, 3]}
    assert cache.read_bytes() == cache_before


class FakeQdrant:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def set_payload(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_qdrant_updates_only_page_payload_after_local_plan(tmp_path: Path) -> None:
    _write_fixture(
        tmp_path,
        ["cover", "first unique text", "second unique text"],
        [
            _chunk("one", "first unique text"),
            _chunk("two", "second unique text"),
        ],
    )
    plans = build_repair_plan(tmp_path)
    client = FakeQdrant()

    updated = await update_qdrant_page_payloads(plans, client)  # type: ignore[arg-type]

    assert updated == 2
    assert {tuple(sorted(call["payload"].items())) for call in client.calls} == {
        (("page_end", 2), ("page_start", 2)),
        (("page_end", 3), ("page_start", 3)),
    }
    assert all(set(call["payload"]) == {"page_start", "page_end"} for call in client.calls)


@pytest.mark.asyncio
async def test_update_qdrant_requires_explicit_apply(tmp_path: Path) -> None:
    args = SimpleNamespace(
        corpus_root=tmp_path,
        document_id=None,
        limit=None,
        apply=False,
        update_qdrant=True,
    )

    with pytest.raises(ValueError, match="requires --apply"):
        await run(args)
