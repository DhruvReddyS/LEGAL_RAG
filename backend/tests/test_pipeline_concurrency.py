from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path

from app.ingestion.metadata import CanonicalDocument
from app.ingestion.pipeline import CheckpointStore, select_shard


def _document(index: int) -> CanonicalDocument:
    return CanonicalDocument.model_construct(
        document_id=f"document-{index}",
        canonical_document_id=f"canonical-{index}",
        sha256=f"{index:064x}",
    )


def _mark_completed(checkpoint_path: str, index: int) -> None:
    CheckpointStore(Path(checkpoint_path)).mark_completed(_document(index), index + 1)


def _hold_claim(
    checkpoint_path: str,
    index: int,
    acquired: multiprocessing.synchronize.Event,
    release: multiprocessing.synchronize.Event,
) -> None:
    with CheckpointStore(Path(checkpoint_path)).claim(_document(index)) as claimed:
        if claimed:
            acquired.set()
            release.wait(timeout=10)


def _try_claim(
    checkpoint_path: str,
    index: int,
    result: multiprocessing.queues.Queue,
) -> None:
    with CheckpointStore(Path(checkpoint_path)).claim(_document(index)) as claimed:
        result.put(claimed)


def _crash_with_claim(
    checkpoint_path: str,
    index: int,
    acquired: multiprocessing.synchronize.Event,
) -> None:
    with CheckpointStore(Path(checkpoint_path)).claim(_document(index)) as claimed:
        if not claimed:
            os._exit(2)
        acquired.set()
        os._exit(17)


def test_select_shard_is_deterministic_disjoint_and_complete() -> None:
    documents = [_document(index) for index in range(11)]

    shards = [
        select_shard(documents, shard_index=index, shard_count=3)
        for index in range(3)
    ]

    assert [[item.document_id for item in shard] for shard in shards] == [
        ["document-0", "document-3", "document-6", "document-9"],
        ["document-1", "document-4", "document-7", "document-10"],
        ["document-2", "document-5", "document-8"],
    ]
    assert {item.document_id for shard in shards for item in shard} == {
        item.document_id for item in documents
    }


def test_stale_store_instances_merge_checkpoint_updates(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "ingestion_checkpoint.json"
    first = CheckpointStore(checkpoint_path)
    second = CheckpointStore(checkpoint_path)

    first.mark_completed(_document(1), 2)
    second.mark_completed(_document(2), 3)

    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert set(checkpoint["completed"]) == {"canonical-1", "canonical-2"}


def test_parallel_processes_do_not_lose_checkpoint_entries(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "ingestion_checkpoint.json"
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(target=_mark_completed, args=(str(checkpoint_path), index))
        for index in range(8)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert set(checkpoint["completed"]) == {
        f"canonical-{index}" for index in range(8)
    }
    assert checkpoint["failed"] == {}


def test_late_failure_cannot_override_success_for_same_checksum(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "ingestion_checkpoint.json"
    document = _document(1)
    completed_store = CheckpointStore(checkpoint_path)
    stale_store = CheckpointStore(checkpoint_path)

    completed_store.mark_completed(document, 2)
    stale_store.mark_failed(document, RuntimeError("late worker failure"))

    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert document.canonical_document_id in checkpoint["completed"]
    assert document.canonical_document_id not in checkpoint["failed"]


def test_document_claim_is_exclusive_and_nonblocking_across_processes(
    tmp_path: Path,
) -> None:
    checkpoint_path = tmp_path / "ingestion_checkpoint.json"
    context = multiprocessing.get_context("spawn")
    acquired = context.Event()
    release = context.Event()
    result = context.Queue()
    holder = context.Process(
        target=_hold_claim,
        args=(str(checkpoint_path), 1, acquired, release),
    )
    contender = context.Process(
        target=_try_claim,
        args=(str(checkpoint_path), 1, result),
    )

    holder.start()
    assert acquired.wait(timeout=10)
    contender.start()
    contender.join(timeout=10)
    assert contender.exitcode == 0
    assert result.get(timeout=2) is False

    release.set()
    holder.join(timeout=10)
    assert holder.exitcode == 0

    with CheckpointStore(checkpoint_path).claim(_document(1)) as claimed:
        assert claimed is True


def test_document_claim_is_released_when_worker_crashes(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "ingestion_checkpoint.json"
    context = multiprocessing.get_context("spawn")
    acquired = context.Event()
    worker = context.Process(
        target=_crash_with_claim,
        args=(str(checkpoint_path), 1, acquired),
    )

    worker.start()
    assert acquired.wait(timeout=10)
    worker.join(timeout=10)
    assert worker.exitcode == 17

    with CheckpointStore(checkpoint_path).claim(_document(1)) as claimed:
        assert claimed is True


def test_busy_document_does_not_block_claiming_another_document(
    tmp_path: Path,
) -> None:
    checkpoint_path = tmp_path / "ingestion_checkpoint.json"
    context = multiprocessing.get_context("spawn")
    acquired = context.Event()
    release = context.Event()
    holder = context.Process(
        target=_hold_claim,
        args=(str(checkpoint_path), 1, acquired, release),
    )

    holder.start()
    assert acquired.wait(timeout=10)
    store = CheckpointStore(checkpoint_path)
    with store.claim(_document(1)) as first_claimed:
        assert first_claimed is False
    with store.claim(_document(2)) as second_claimed:
        assert second_claimed is True

    release.set()
    holder.join(timeout=10)
    assert holder.exitcode == 0
