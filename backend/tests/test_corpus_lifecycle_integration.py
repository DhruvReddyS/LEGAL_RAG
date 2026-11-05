"""CORP-04: add, replace and retire, against a real vector store and temp manifests.

Qdrant is the throwaway stack's, each test has its own uniquely named collection,
and the manifest is a temporary file. The stores are read back directly afterwards:
being told the points are gone by the code that deleted them would prove nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from qdrant_client import models

from app.core.config import settings
from app.core.qdrant import create_qdrant_client
from app.ingestion import lifecycle, pipeline, qdrant_writer
from app.ingestion.embedder import EmbeddedText
from app.ingestion.init_qdrant import POLICE_CASE_DATA
from app.ingestion.lifecycle import IngestionProcess, LifecycleRefused

pytestmark = pytest.mark.integration


def no_processes() -> list[IngestionProcess]:
    return []


@pytest.fixture(autouse=True)
def _throwaway_qdrant_only() -> None:
    # Hosted CI's Qdrant is a service container that lives only for the job.
    throwaway = settings.qdrant_url.endswith(":56333") or os.environ.get("GITHUB_ACTIONS") == "true"
    assert throwaway, "this suite deletes points: throwaway Qdrant only"


@pytest_asyncio.fixture(loop_scope="session")
async def qdrant():
    client = create_qdrant_client()
    yield client
    await client.close()


@pytest_asyncio.fixture(loop_scope="session")
async def collection(qdrant):
    name = f"lifecycle_test_{uuid.uuid4().hex[:12]}"
    await qdrant.create_collection(
        collection_name=name,
        vectors_config={
            settings.qdrant_dense_vector_name: models.VectorParams(
                size=settings.embedding_dimension, distance=models.Distance.COSINE
            )
        },
        sparse_vectors_config={settings.qdrant_sparse_vector_name: models.SparseVectorParams()},
    )
    yield name
    await qdrant.delete_collection(name)


def _pdf(path: Path, text: str) -> bytes:
    import pymupdf

    path.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open()
    for page_number in range(2):
        page = document.new_page()
        page.insert_textbox(
            pymupdf.Rect(60, 60, 540, 780),
            f"THE {text.upper()} ACT, 2026\n\n"
            + "\n\n".join(
                f"{n + 1 + page_number * 10}. Duty {n}. Every registered person under the {text} Act "
                f"shall keep a true record of the matters required by this section, and shall "
                f"produce that record to the authority when lawfully asked to do so."
                for n in range(6)
            ),
            fontsize=10,
        )
    document.save(path)
    document.close()
    return path.read_bytes()


def _row(root: Path, slug: str) -> dict:
    relative = f"raw/primary_law/{slug}/{slug}.pdf"
    content = _pdf(root / relative, slug)
    checksum = hashlib.sha256(content).hexdigest()
    return {
        "act_name": f"The {slug} Act, 2026",
        "authority": "Test authority",
        "canonical_document_id": f"test-canonical-{checksum[:24]}",
        "category": "primary_law/test",
        "current_status": "current/verify",
        "document_id": f"test-doc-{slug}",
        "file_size": len(content),
        "jurisdiction": "India - Central",
        "local_path": relative,
        "original_filename": f"{slug}.pdf",
        "page_count": 2,
        "quality_status": "verified",
        "sha256": checksum,
        "source_id": slug,
        "source_type": "act",
        "title": f"The {slug} Act, 2026",
        "verified_official": True,
    }


def _write_manifest(root: Path, rows: list[dict]) -> Path:
    path = root / "metadata/canonical_documents.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    return path


class FakeEmbedder:
    """Everything real but the model, which this machine is busy with."""

    model_name = "fake-embedder"

    def embed_texts(self, texts, *, batch_size, on_batch=None, start_index=0):
        result = []
        for index, text in enumerate(texts):
            seed = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
            dense = [0.0] * settings.embedding_dimension
            dense[seed % settings.embedding_dimension] = 1.0
            result.append(EmbeddedText(dense=dense, sparse={seed % 1000: 1.0}))
            if on_batch:
                on_batch(start_index + index, [result[-1]])
        return result


@pytest.fixture
def real_pipeline(monkeypatch, collection):
    """The real run_pipeline, in process, aimed at this test's collection and corpus."""

    async def initialized() -> None:
        return None

    monkeypatch.setattr(settings, "qdrant_global_collection", collection)
    monkeypatch.setattr(qdrant_writer, "GLOBAL_LEGAL_CORPUS", collection)
    monkeypatch.setattr(pipeline, "BGEM3Embedder", FakeEmbedder)
    monkeypatch.setattr(pipeline, "initialize_qdrant", initialized)

    async def run(root: Path, named: str, canonical_id: str) -> None:
        assert named == collection
        await pipeline.run_pipeline(
            pipeline.PipelineOptions(resume=True, document_id=canonical_id), corpus_root=root
        )

    return run


async def _points(client, collection: str, canonical_id: str) -> int:
    return (
        await client.count(
            collection,
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="canonical_document_id", match=models.MatchValue(value=canonical_id)
                    )
                ]
            ),
            exact=True,
        )
    ).count


def _ledger(root: Path, collection: str) -> dict:
    return json.loads(pipeline.checkpoint_path_for(root, collection).read_text())


# ------------------------------------------------------------------------- add


async def test_add_indexes_through_the_real_pipeline_and_confirms(tmp_path, qdrant, collection, real_pipeline):
    row = _row(tmp_path, "alpha")
    _write_manifest(tmp_path, [row])
    cid = row["canonical_document_id"]

    plan = await lifecycle.plan_add(tmp_path, collection, cid, qdrant)
    assert not plan.already_indexed and plan.points == 0

    result = await lifecycle.execute_add(
        tmp_path, collection, cid, qdrant, runner=real_pipeline, lister=no_processes
    )

    stored = await _points(qdrant, collection, cid)
    assert stored > 0 and result["points"] == stored
    assert _ledger(tmp_path, collection)["completed"][cid]["chunk_count"] == stored
    # Running it again finds the work done rather than doing it again.
    again = await lifecycle.plan_add(tmp_path, collection, cid, qdrant)
    assert again.already_indexed


async def test_add_from_a_staged_manifest_appends_only_that_row(tmp_path, qdrant, collection, real_pipeline):
    existing = _row(tmp_path, "alpha")
    staged_row = _row(tmp_path, "beta")
    manifest = _write_manifest(tmp_path, [existing])
    before = manifest.read_text()
    staged = tmp_path / "staged.jsonl"
    staged.write_text(json.dumps({**staged_row, "licence": "kept extra field"}) + "\n")

    await lifecycle.execute_add(
        tmp_path,
        collection,
        staged_row["document_id"],
        qdrant,
        from_manifest=staged,
        runner=real_pipeline,
        lister=no_processes,
    )

    after = manifest.read_text()
    assert after.startswith(before)
    added = json.loads(after[len(before) :])
    assert added["canonical_document_id"] == staged_row["canonical_document_id"]
    assert added["licence"] == "kept extra field"


async def test_add_refuses_a_file_that_fails_its_checksum(tmp_path, qdrant, collection):
    row = _row(tmp_path, "alpha")
    _write_manifest(tmp_path, [{**row, "sha256": "0" * 64}])
    with pytest.raises(LifecycleRefused, match="Checksum mismatch"):
        await lifecycle.plan_add(tmp_path, collection, row["document_id"], qdrant)


async def test_a_pipeline_that_selects_nothing_is_not_a_success(tmp_path, qdrant, collection):
    row = _row(tmp_path, "alpha")
    _write_manifest(tmp_path, [row])

    def does_nothing(*_args) -> None:
        return None

    with pytest.raises(LifecycleRefused, match="not marked complete"):
        await lifecycle.execute_add(
            tmp_path, collection, row["document_id"], qdrant, runner=does_nothing, lister=no_processes
        )


async def test_a_ledger_that_disagrees_with_the_index_is_not_confirmed(tmp_path, qdrant, collection):
    row = _row(tmp_path, "alpha")
    _write_manifest(tmp_path, [row])
    cid = row["canonical_document_id"]

    def claims_success_without_points(root, named, canonical_id) -> None:
        ledger = pipeline.checkpoint_path_for(root, named)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            json.dumps({"completed": {canonical_id: {"sha256": row["sha256"], "chunk_count": 5}}, "failed": {}})
        )

    with pytest.raises(LifecycleRefused, match="records 5 chunks"):
        await lifecycle.execute_add(
            tmp_path, collection, cid, qdrant, runner=claims_success_without_points, lister=no_processes
        )


def test_the_real_runner_names_the_collection_and_corpus(tmp_path) -> None:
    environment = lifecycle.pipeline_environment(tmp_path, "some_collection")
    assert environment["QDRANT_GLOBAL_COLLECTION"] == "some_collection"
    assert environment["LEGAL_KB_ROOT"] == str(tmp_path)
    assert lifecycle.pipeline_command("abc")[1:] == [
        "-m",
        "app.ingestion.pipeline",
        "--resume",
        "--document-id",
        "abc",
    ]


def test_the_real_runner_passes_the_environment_and_reports_failure(tmp_path, monkeypatch) -> None:
    """A real child process, standing in for the pipeline so the model stays unloaded."""
    seen = tmp_path / "seen.json"
    script = (
        "import json, os, sys; "
        f"json.dump({{k: os.environ[k] for k in ('QDRANT_GLOBAL_COLLECTION', 'LEGAL_KB_ROOT')}}, open({str(seen)!r}, 'w')); "
        "sys.exit(int(sys.argv[1]))"
    )
    monkeypatch.setattr(lifecycle, "pipeline_command", lambda _cid: [sys.executable, "-c", script, "3"])
    with pytest.raises(LifecycleRefused, match="exited 3"):
        lifecycle.run_pipeline_subprocess(tmp_path, "some_collection", "abc")
    assert json.loads(seen.read_text()) == {
        "QDRANT_GLOBAL_COLLECTION": "some_collection",
        "LEGAL_KB_ROOT": str(tmp_path),
    }

    monkeypatch.setattr(lifecycle, "pipeline_command", lambda _cid: [sys.executable, "-c", script, "0"])
    lifecycle.run_pipeline_subprocess(tmp_path, "some_collection", "abc")


async def test_pending_lists_only_what_this_collection_has_not_completed(tmp_path, qdrant, collection, real_pipeline):
    alpha, beta = _row(tmp_path, "alpha"), _row(tmp_path, "beta")
    _write_manifest(tmp_path, [alpha, beta])
    await lifecycle.execute_add(
        tmp_path, collection, alpha["document_id"], qdrant, runner=real_pipeline, lister=no_processes
    )
    pending = lifecycle.pending_documents(tmp_path, collection)
    assert [item.canonical_document_id for item in pending] == [beta["canonical_document_id"]]
    assert [item.canonical_document_id for item in lifecycle.pending_documents(tmp_path, "another")] == [
        alpha["canonical_document_id"],
        beta["canonical_document_id"],
    ]


# ---------------------------------------------------------------------- retire


async def test_retire_removes_every_trace_and_leaves_the_neighbour(tmp_path, qdrant, collection, real_pipeline):
    alpha, beta = _row(tmp_path, "alpha"), _row(tmp_path, "beta")
    duplicate = {**alpha, "document_id": "test-doc-alpha-copy", "local_path": alpha["local_path"]}
    manifest = _write_manifest(tmp_path, [alpha, duplicate, beta])
    for row in (alpha, beta):
        await lifecycle.execute_add(
            tmp_path, collection, row["document_id"], qdrant, runner=real_pipeline, lister=no_processes
        )
    alpha_id, beta_id = alpha["canonical_document_id"], beta["canonical_document_id"]
    beta_line = next(line for line in manifest.read_text().splitlines(True) if beta_id in line)
    beta_points = await _points(qdrant, collection, beta_id)
    chunk_file = pipeline.chunks_dir_for(tmp_path, collection) / f"{alpha_id}.jsonl"
    assert chunk_file.exists()
    alpha_points = await _points(qdrant, collection, alpha_id)

    plan = await lifecycle.plan_retire(tmp_path, collection, alpha_id, qdrant)
    assert plan.points == alpha_points
    assert len(plan.manifest_rows) == 2
    assert await _points(qdrant, collection, alpha_id) == alpha_points, "planning changed nothing"

    result = await lifecycle.execute_retire(tmp_path, collection, alpha_id, qdrant, lister=no_processes)

    assert result["points_removed"] == alpha_points
    assert await _points(qdrant, collection, alpha_id) == 0
    assert await _points(qdrant, collection, beta_id) == beta_points
    assert manifest.read_text() == beta_line, "the neighbour's bytes are untouched"
    ledger = _ledger(tmp_path, collection)
    assert alpha_id not in ledger["completed"] and beta_id in ledger["completed"]
    assert not chunk_file.exists()
    assert (tmp_path / alpha["local_path"]).exists(), "the source PDF stays"
    log = (tmp_path / "logs/corpus_lifecycle.jsonl").read_text().splitlines()
    assert len(json.loads(log[-1])["manifest_rows_removed"]) == 2, "enough to put it back"


async def test_a_mistyped_id_removes_nothing_and_says_so(tmp_path, qdrant, collection):
    manifest = _write_manifest(tmp_path, [_row(tmp_path, "alpha")])
    before = manifest.read_text()
    with pytest.raises(LifecycleRefused, match="Check the id"):
        await lifecycle.execute_retire(tmp_path, collection, "no-such-id", qdrant, lister=no_processes)
    assert manifest.read_text() == before


async def test_a_mistyped_collection_is_refused_rather_than_created(tmp_path, qdrant):
    row = _row(tmp_path, "alpha")
    _write_manifest(tmp_path, [row])
    name = f"lifecycle_absent_{uuid.uuid4().hex[:8]}"
    with pytest.raises(LifecycleRefused, match="does not exist"):
        await lifecycle.plan_add(tmp_path, name, row["document_id"], qdrant)
    assert not await qdrant.collection_exists(name)


async def test_case_evidence_collections_are_refused(tmp_path, qdrant):
    _write_manifest(tmp_path, [])
    with pytest.raises(LifecycleRefused, match="private case evidence"):
        await lifecycle.plan_retire(tmp_path, POLICE_CASE_DATA, "anything", qdrant)


async def test_a_failed_delete_changes_nothing_else(tmp_path, qdrant, collection, real_pipeline):
    row = _row(tmp_path, "alpha")
    manifest = _write_manifest(tmp_path, [row])
    cid = row["canonical_document_id"]
    await lifecycle.execute_add(tmp_path, collection, cid, qdrant, runner=real_pipeline, lister=no_processes)
    before = manifest.read_text()

    class DeleteFails:
        def __getattr__(self, name):
            return getattr(qdrant, name)

        async def delete(self, **_kwargs):
            raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        await lifecycle.execute_retire(tmp_path, collection, cid, DeleteFails(), lister=no_processes)

    assert manifest.read_text() == before
    assert cid in _ledger(tmp_path, collection)["completed"]
    assert await _points(qdrant, collection, cid) > 0


# --------------------------------------------------------------------- replace


async def test_replace_retires_only_after_the_new_copy_is_confirmed(tmp_path, qdrant, collection, real_pipeline):
    old, new = _row(tmp_path, "old"), _row(tmp_path, "new")
    manifest = _write_manifest(tmp_path, [old, new])
    old_id, new_id = old["canonical_document_id"], new["canonical_document_id"]
    await lifecycle.execute_add(tmp_path, collection, old_id, qdrant, runner=real_pipeline, lister=no_processes)

    result = await lifecycle.execute_replace(
        tmp_path, collection, old_id, new_id, qdrant, runner=real_pipeline, lister=no_processes
    )

    assert result["added"]["points"] == await _points(qdrant, collection, new_id) > 0
    assert await _points(qdrant, collection, old_id) == 0
    assert old_id not in manifest.read_text() and new_id in manifest.read_text()


async def test_replace_keeps_the_old_copy_when_the_new_one_fails(tmp_path, qdrant, collection, real_pipeline):
    old, new = _row(tmp_path, "old"), _row(tmp_path, "new")
    manifest = _write_manifest(tmp_path, [old, new])
    old_id, new_id = old["canonical_document_id"], new["canonical_document_id"]
    await lifecycle.execute_add(tmp_path, collection, old_id, qdrant, runner=real_pipeline, lister=no_processes)
    old_points = await _points(qdrant, collection, old_id)

    def fails(*_args) -> None:
        raise LifecycleRefused("The pipeline exited 1")

    with pytest.raises(LifecycleRefused):
        await lifecycle.execute_replace(tmp_path, collection, old_id, new_id, qdrant, runner=fails, lister=no_processes)
    assert await _points(qdrant, collection, old_id) == old_points
    assert old_id in manifest.read_text()
    assert old_id in _ledger(tmp_path, collection)["completed"]

    def no_points(*_args) -> None:
        return None

    with pytest.raises(LifecycleRefused, match="not marked complete"):
        await lifecycle.execute_replace(tmp_path, collection, old_id, new_id, qdrant, runner=no_points, lister=no_processes)
    assert await _points(qdrant, collection, old_id) == old_points


async def test_replacing_a_document_with_itself_is_refused(tmp_path, qdrant, collection):
    row = _row(tmp_path, "alpha")
    _write_manifest(tmp_path, [row])
    cid = row["canonical_document_id"]
    with pytest.raises(LifecycleRefused, match="same document"):
        await lifecycle.plan_replace(tmp_path, collection, cid, cid, qdrant)


# ----------------------------------------------------------- refuses to overlap


def _process(*, collection: str | None, kb_root: str | None) -> IngestionProcess:
    return IngestionProcess(pid=1, command="python -m app.ingestion.pipeline", collection=collection, kb_root=kb_root)


def test_what_counts_as_blocking(tmp_path) -> None:
    other_root = str(tmp_path / "elsewhere")
    root = str(tmp_path)
    cases = [
        (_process(collection="c", kb_root=other_root), True),  # this collection
        (_process(collection=None, kb_root=other_root), True),  # cannot tell which
        (_process(collection="other", kb_root=root), True),  # shares this manifest
        (_process(collection="other", kb_root=None), True),  # may share it
        (_process(collection="other", kb_root=other_root), False),
        (_process(collection="c", kb_root="<supervisor>"), True),
        (_process(collection="other", kb_root="<supervisor>"), False),
    ]
    for process, blocks in cases:
        assert bool(lifecycle.blocking_processes([process], collection="c", root=tmp_path)) is blocks, process


def test_environment_values_with_spaces_in_them_are_read_whole() -> None:
    output = "PID TT STAT TIME COMMAND\n1 ?? R 0:01 python -m x A=1 LEGAL_KB_ROOT=/Users/me/MAJOR PROJECT/data/legal_kb QDRANT_GLOBAL_COLLECTION=v6 B=2"
    assert lifecycle._environment_value(output, "LEGAL_KB_ROOT") == "/Users/me/MAJOR PROJECT/data/legal_kb"
    assert lifecycle._environment_value(output, "QDRANT_GLOBAL_COLLECTION") == "v6"


async def test_a_real_running_pipeline_process_blocks_every_write(tmp_path, qdrant, collection, real_pipeline):
    """An actual process, found by the real `ps` scan, carrying the name in its environment."""
    row = _row(tmp_path, "alpha")
    manifest = _write_manifest(tmp_path, [row])
    cid = row["canonical_document_id"]
    await lifecycle.execute_add(tmp_path, collection, cid, qdrant, runner=real_pipeline, lister=no_processes)
    before = manifest.read_text()
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)", "-m", "app.ingestion.pipeline"],
        env={**os.environ, "QDRANT_GLOBAL_COLLECTION": collection, "LEGAL_KB_ROOT": str(tmp_path)},
    )
    try:
        deadline = time.time() + 5
        while time.time() < deadline and not any(
            item.pid == process.pid and item.collection == collection
            for item in lifecycle.list_ingestion_processes()
        ):
            time.sleep(0.1)
        with pytest.raises(LifecycleRefused, match="while ingestion is running"):
            await lifecycle.execute_retire(tmp_path, collection, cid, qdrant)
        with pytest.raises(LifecycleRefused, match="while ingestion is running"):
            await lifecycle.execute_add(tmp_path, collection, cid, qdrant)
    finally:
        process.kill()
        process.wait()
    assert manifest.read_text() == before
    assert await _points(qdrant, collection, cid) > 0


async def test_a_held_document_claim_blocks_whatever_the_process_table_says(tmp_path, qdrant, collection):
    import fcntl

    row = _row(tmp_path, "alpha")
    _write_manifest(tmp_path, [row])
    ledger = pipeline.checkpoint_path_for(tmp_path, collection)
    claims = ledger.parent / f"{ledger.stem}_claims"
    claims.mkdir(parents=True)
    claim = (claims / "held.lock").open("a+")
    # flock is per open file description, so this conflicts with the check's own open.
    fcntl.flock(claim.fileno(), fcntl.LOCK_EX)
    try:
        assert lifecycle.claims_held(tmp_path, collection) == 1
        with pytest.raises(LifecycleRefused, match="claim"):
            await lifecycle.execute_retire(tmp_path, collection, row["canonical_document_id"], qdrant, lister=no_processes)
    finally:
        fcntl.flock(claim.fileno(), fcntl.LOCK_UN)
        claim.close()
    assert lifecycle.claims_held(tmp_path, collection) == 0


# ------------------------------------------------------------------------- CLI


def _load_cli():
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "scripts/corpus_lifecycle.py"
    spec = importlib.util.spec_from_file_location("corpus_lifecycle_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "arguments",
    [
        ["retire", "--document-id", "x"],
        ["add", "--document-id", "x"],
        ["replace", "--old", "x", "--new", "y"],
    ],
)
def test_the_collection_is_never_defaulted(arguments, capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        _load_cli().parse_args(arguments)
    assert raised.value.code == 2
    assert "--collection" in capsys.readouterr().err


async def test_retire_dry_run_prints_the_plan_and_changes_nothing(tmp_path, qdrant, collection, real_pipeline, capsys):
    row = _row(tmp_path, "alpha")
    manifest = _write_manifest(tmp_path, [row])
    cid = row["canonical_document_id"]
    await lifecycle.execute_add(tmp_path, collection, cid, qdrant, runner=real_pipeline, lister=no_processes)
    points = await _points(qdrant, collection, cid)
    before, ledger_before = manifest.read_text(), _ledger(tmp_path, collection)
    cli = _load_cli()

    code = await cli.run(
        cli.parse_args(["retire", "--collection", collection, "--document-id", cid, "--dry-run", "--kb-root", str(tmp_path)])
    )

    output = capsys.readouterr().out
    assert code == 0
    assert f"delete {points} point(s)" in output and "dry run: nothing changed" in output
    assert manifest.read_text() == before
    assert _ledger(tmp_path, collection) == ledger_before
    assert await _points(qdrant, collection, cid) == points


async def test_the_cli_retires_when_told_to(tmp_path, qdrant, collection, real_pipeline, monkeypatch, capsys):
    row = _row(tmp_path, "alpha")
    manifest = _write_manifest(tmp_path, [row])
    cid = row["canonical_document_id"]
    await lifecycle.execute_add(tmp_path, collection, cid, qdrant, runner=real_pipeline, lister=no_processes)
    monkeypatch.setattr(lifecycle, "list_ingestion_processes", no_processes)
    monkeypatch.setattr(lifecycle.execute_retire, "__kwdefaults__", {"lister": no_processes})
    cli = _load_cli()

    code = await cli.run(
        cli.parse_args(["retire", "--collection", collection, "--document-id", cid, "--yes", "--kb-root", str(tmp_path)])
    )

    assert code == 0, capsys.readouterr().err
    assert await _points(qdrant, collection, cid) == 0
    assert manifest.read_text() == ""


async def test_pending_dry_run_lists_without_running(tmp_path, qdrant, collection, capsys):
    row = _row(tmp_path, "alpha")
    _write_manifest(tmp_path, [row])
    cli = _load_cli()
    code = await cli.run(
        cli.parse_args(["add", "--collection", collection, "--pending", "--dry-run", "--kb-root", str(tmp_path)])
    )
    output = capsys.readouterr().out
    assert code == 0
    assert "1 document(s) pending" in output and row["canonical_document_id"] in output
    assert "dry run: nothing changed" in output
    assert await _points(qdrant, collection, row["canonical_document_id"]) == 0


async def test_the_cli_will_not_retire_without_being_told_to(tmp_path, qdrant, collection, real_pipeline, monkeypatch):
    row = _row(tmp_path, "alpha")
    _write_manifest(tmp_path, [row])
    cid = row["canonical_document_id"]
    await lifecycle.execute_add(tmp_path, collection, cid, qdrant, runner=real_pipeline, lister=no_processes)
    monkeypatch.setattr(sys, "stdin", open(os.devnull))
    cli = _load_cli()
    code = await cli.run(cli.parse_args(["retire", "--collection", collection, "--document-id", cid, "--kb-root", str(tmp_path)]))
    assert code == 1
    assert await _points(qdrant, collection, cid) > 0
