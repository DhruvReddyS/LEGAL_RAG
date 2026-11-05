"""Add, replace and retire one corpus document without a rebuild.

The collection is always named by the caller. Every other ingestion entry point
falls back to `settings.qdrant_global_collection`, which is the right default for
a process that builds an index and the wrong one for a process that deletes from
it: a forgotten argument would remove law from whatever happens to be serving.

Retiring goes through the stores in the order `services/privacy.py` uses. The
vector store is the part that can fail, so it goes first. If it is down nothing
has changed, and if the process dies later the same command finishes the job,
because every step is safe to repeat. The manifest row goes last and is written
to the lifecycle log in full, so a mistaken retirement can be put back.

Nothing here runs while an ingestion process could be reading the same files. A
rebuild counts the manifest once at startup and loops until its ledger reaches
that count, so even a retirement against a different collection would leave it
retrying a target it can no longer reach.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Awaitable, Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qdrant_client import models

from app.ingestion.dedup import verify_document_checksum
from app.ingestion.init_qdrant import ADVOCATE_CASE_DATA, POLICE_CASE_DATA
from app.ingestion.metadata import CanonicalDocument, iter_canonical_documents, load_manifest
from app.ingestion.pipeline import CheckpointStore, checkpoint_path_for, chunks_dir_for

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_RELATIVE = Path("metadata/canonical_documents.jsonl")
LOG_RELATIVE = Path("logs/corpus_lifecycle.jsonl")
# The payload key `qdrant_writer.legal_chunk_payload` writes on every point.
DOCUMENT_KEY = "canonical_document_id"
# Case evidence is erased by case_id through the privacy service, never from here.
_REFUSED_COLLECTIONS = frozenset({POLICE_CASE_DATA, ADVOCATE_CASE_DATA})

_INGESTION_MODULE_RE = re.compile(
    r"-m\s+app\.ingestion\.(?:pipeline|restore_chunks|repair_metadata|repair_page_ranges)\b"
)
_REBUILD_RE = re.compile(r"run_rebuild\.sh(?:\s+([A-Za-z0-9_.-]+))?")
# run_rebuild.sh's own default when it is given no argument.
_REBUILD_DEFAULT_COLLECTION = "global_legal_corpus_v2"


class LifecycleRefused(RuntimeError):
    """The operation was not attempted or did not complete, and says why."""


# ------------------------------------------------------- is ingestion running


@dataclass(frozen=True)
class IngestionProcess:
    pid: int
    command: str
    collection: str | None
    kb_root: str | None


def _environment_value(environment: str, name: str) -> str | None:
    # `ps e` joins values with spaces, and this project's path contains one, so a
    # value runs up to the next NAME= rather than the next space.
    match = re.search(
        rf"(?:^|\s){name}=(.*?)(?=\s+[A-Za-z_][A-Za-z0-9_]*=|$)", environment, re.S
    )
    return match.group(1) if match else None


def _process_environment(pid: int) -> str:
    proc = Path(f"/proc/{pid}/environ")
    try:
        if proc.exists():
            return proc.read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        result = subprocess.run(
            ["ps", "eww", "-p", str(pid)], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def list_ingestion_processes() -> list[IngestionProcess]:
    """Every process that may be writing a collection, as far as can be told.

    A failure to list is a refusal rather than an empty list: "could not check" must
    not read as "nothing is running" to a tool that deletes.
    """
    try:
        result = subprocess.run(
            ["ps", "-axww", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LifecycleRefused(
            f"Could not list processes to check for a running ingestion: {type(exc).__name__}"
        ) from exc
    if result.returncode != 0:
        raise LifecycleRefused("Could not list processes to check for a running ingestion.")

    own = {os.getpid(), os.getppid()}
    found: list[IngestionProcess] = []
    for line in result.stdout.splitlines():
        pid_text, _, command = line.strip().partition(" ")
        if not pid_text.isdigit() or int(pid_text) in own:
            continue
        rebuild = _REBUILD_RE.search(command)
        if rebuild:
            found.append(
                IngestionProcess(
                    pid=int(pid_text),
                    command=command[:160],
                    collection=rebuild.group(1) or _REBUILD_DEFAULT_COLLECTION,
                    # The supervisor always works on its own checkout's corpus and
                    # its pipeline child carries the path, so it is judged on the
                    # collection alone.
                    kb_root="<supervisor>",
                )
            )
        elif _INGESTION_MODULE_RE.search(command):
            environment = _process_environment(int(pid_text))
            found.append(
                IngestionProcess(
                    pid=int(pid_text),
                    command=command[:160],
                    collection=_environment_value(environment, "QDRANT_GLOBAL_COLLECTION"),
                    kb_root=_environment_value(environment, "LEGAL_KB_ROOT"),
                )
            )
    return found


def blocking_processes(
    processes: Iterable[IngestionProcess], *, collection: str, root: Path
) -> list[IngestionProcess]:
    """Which of these make it unsafe to change this collection or this manifest."""
    resolved_root = str(root.resolve())
    blocking: list[IngestionProcess] = []
    for process in processes:
        if process.collection == collection or process.collection is None:
            blocking.append(process)
        elif process.kb_root == "<supervisor>":
            continue
        elif process.kb_root is None or str(Path(process.kb_root).resolve()) == resolved_root:
            # Another collection, but the same manifest.
            blocking.append(process)
    return blocking


def claims_held(root: Path, collection: str) -> int:
    """Documents a live worker holds in this collection's ledger right now.

    The one signal that cannot be fooled by how a process was started: the claim is
    an flock the pipeline holds for as long as it works on a document, and the kernel
    releases it when the process dies.
    """
    ledger = checkpoint_path_for(root, collection)
    claims = ledger.parent / f"{ledger.stem}_claims"
    held = 0
    if not claims.is_dir():
        return 0
    for path in claims.glob("*.lock"):
        with path.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                    raise
                held += 1
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return held


def ingestion_blockers(
    root: Path,
    collection: str,
    *,
    lister: Callable[[], list[IngestionProcess]] = list_ingestion_processes,
) -> list[str]:
    reasons = [
        f"pid {process.pid} ({process.collection or 'collection unknown'}): {process.command}"
        for process in blocking_processes(lister(), collection=collection, root=root)
    ]
    held = claims_held(root, collection)
    if held:
        reasons.append(f"{held} document claim(s) held in the {collection} ledger")
    return reasons


def _refuse_if_ingesting(
    root: Path, collection: str, lister: Callable[[], list[IngestionProcess]]
) -> None:
    reasons = ingestion_blockers(root, collection, lister=lister)
    if reasons:
        raise LifecycleRefused(
            "Refusing to run while ingestion is running:\n  " + "\n  ".join(reasons)
        )


# --------------------------------------------------------------------- files


def _write_atomic(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _manifest_lock(root: Path):
    """One lifecycle command at a time per corpus. Blocks rather than races."""
    lock_path = root / "logs/corpus_lifecycle.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _manifest_lines(root: Path) -> list[str]:
    path = root / MANIFEST_RELATIVE
    if not path.is_file():
        raise LifecycleRefused(f"No manifest at {path}")
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def _rows_for(root: Path, canonical_id: str) -> list[dict[str, Any]]:
    return [
        row
        for row in (json.loads(line) for line in _manifest_lines(root) if line.strip())
        if row.get(DOCUMENT_KEY) == canonical_id
    ]


def _remove_manifest_rows(root: Path, canonical_id: str) -> list[dict[str, Any]]:
    """Filter by line, so every row that stays keeps its exact bytes."""
    kept: list[str] = []
    removed: list[dict[str, Any]] = []
    for line in _manifest_lines(root):
        if line.strip():
            row = json.loads(line)
            if row.get(DOCUMENT_KEY) == canonical_id:
                removed.append(row)
                continue
        kept.append(line)
    if removed:
        _write_atomic(root / MANIFEST_RELATIVE, "".join(kept))
    return removed


def _append_manifest_row(root: Path, row: dict[str, Any]) -> None:
    lines = _manifest_lines(root)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines.append(json.dumps(row, sort_keys=True) + "\n")
    _write_atomic(root / MANIFEST_RELATIVE, "".join(lines))


def _log(root: Path, event: dict[str, Any]) -> None:
    path = root / LOG_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"at": datetime.now(timezone.utc).isoformat(), **event}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_ledger(root: Path, collection: str) -> dict[str, Any]:
    """Without CheckpointStore, whose constructor creates files a dry run must not."""
    path = checkpoint_path_for(root, collection)
    if not path.is_file():
        return {"completed": {}, "failed": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("completed", {})
    data.setdefault("failed", {})
    return data


def _other_ledgers_listing(root: Path, collection: str, canonical_id: str) -> list[str]:
    own = checkpoint_path_for(root, collection).name
    names: list[str] = []
    for path in sorted((root / "logs").glob("ingestion_checkpoint*.json")):
        if path.name == own:
            continue
        try:
            completed = json.loads(path.read_text(encoding="utf-8")).get("completed", {})
        except (OSError, json.JSONDecodeError):
            continue
        if canonical_id in completed:
            names.append(path.name)
    return names


# ------------------------------------------------------------------ the index


def document_filter(canonical_id: str) -> models.Filter:
    return models.Filter(
        must=[models.FieldCondition(key=DOCUMENT_KEY, match=models.MatchValue(value=canonical_id))]
    )


async def count_document_points(client: Any, collection: str, canonical_id: str) -> int:
    result = await client.count(
        collection_name=collection, count_filter=document_filter(canonical_id), exact=True
    )
    return int(result.count)


async def _require_collection(client: Any, collection: str) -> None:
    if collection in _REFUSED_COLLECTIONS:
        raise LifecycleRefused(
            f"{collection} holds private case evidence. It is erased by case, not from here."
        )
    if not await client.collection_exists(collection):
        # Also stops the pipeline's initialize_qdrant from quietly creating an empty
        # collection under a mistyped name.
        raise LifecycleRefused(f"Collection {collection} does not exist.")


# --------------------------------------------------------------------- retire


@dataclass
class RetirePlan:
    collection: str
    canonical_document_id: str
    points: int
    manifest_rows: list[dict[str, Any]]
    ledger_completed: dict[str, Any] | None
    ledger_failed: dict[str, Any] | None
    chunk_file: Path | None
    other_ledgers: list[str] = field(default_factory=list)

    @property
    def nothing_to_do(self) -> bool:
        return not (
            self.points
            or self.manifest_rows
            or self.ledger_completed
            or self.ledger_failed
            or self.chunk_file
        )

    def describe(self) -> list[str]:
        lines = [f"retire {self.canonical_document_id} from {self.collection}"]
        lines.append(f"  delete {self.points} point(s) where {DOCUMENT_KEY} matches")
        lines.append(f"  remove {len(self.manifest_rows)} manifest row(s)")
        for row in self.manifest_rows:
            lines.append(f"    {row.get('document_id')}: {row.get('title')} ({row.get('local_path')})")
        if self.ledger_completed:
            lines.append(
                f"  remove ledger entry ({self.ledger_completed.get('chunk_count')} chunks recorded)"
            )
        if self.ledger_failed:
            lines.append("  remove failed ledger entry")
        if self.chunk_file:
            lines.append(f"  delete derived chunk file {self.chunk_file.name}")
        lines.append("  keep the raw PDF, extracted text and embedding cache")
        if self.other_ledgers:
            lines.append(
                "  note: also indexed in another collection, which this leaves alone: "
                + ", ".join(self.other_ledgers)
            )
        return lines


async def plan_retire(root: Path, collection: str, canonical_id: str, client: Any) -> RetirePlan:
    await _require_collection(client, collection)
    ledger = _read_ledger(root, collection)
    chunk_file = chunks_dir_for(root, collection) / f"{canonical_id}.jsonl"
    return RetirePlan(
        collection=collection,
        canonical_document_id=canonical_id,
        points=await count_document_points(client, collection, canonical_id),
        manifest_rows=_rows_for(root, canonical_id),
        ledger_completed=ledger["completed"].get(canonical_id),
        ledger_failed=ledger["failed"].get(canonical_id),
        chunk_file=chunk_file if chunk_file.exists() else None,
        other_ledgers=_other_ledgers_listing(root, collection, canonical_id),
    )


async def execute_retire(
    root: Path,
    collection: str,
    canonical_id: str,
    client: Any,
    *,
    lister: Callable[[], list[IngestionProcess]] = list_ingestion_processes,
) -> dict[str, Any]:
    with _manifest_lock(root):
        _refuse_if_ingesting(root, collection, lister)
        plan = await plan_retire(root, collection, canonical_id, client)
        if plan.nothing_to_do:
            raise LifecycleRefused(
                f"{canonical_id} is not in the manifest, the ledger or {collection}. "
                "Check the id: this removed nothing."
            )
        await client.delete(
            collection_name=collection,
            points_selector=models.FilterSelector(filter=document_filter(canonical_id)),
            wait=True,
        )
        remaining = await count_document_points(client, collection, canonical_id)
        if remaining:
            raise LifecycleRefused(
                f"{remaining} point(s) remain in {collection} after the delete. "
                "The manifest and ledger were not changed. Run it again."
            )
        ledger_path = checkpoint_path_for(root, collection)
        if ledger_path.is_file():

            def drop(data: dict[str, Any]) -> None:
                data["completed"].pop(canonical_id, None)
                data["failed"].pop(canonical_id, None)

            CheckpointStore(ledger_path)._update(drop)
        if plan.chunk_file:
            plan.chunk_file.unlink(missing_ok=True)
        removed = _remove_manifest_rows(root, canonical_id)
        result = {
            "action": "retire",
            "collection": collection,
            DOCUMENT_KEY: canonical_id,
            "points_removed": plan.points,
            # In full, so a mistaken retirement can be put back by hand.
            "manifest_rows_removed": removed,
            "ledger_entry_removed": plan.ledger_completed,
        }
        _log(root, result)
        return result


# ------------------------------------------------------------------------ add


PipelineRunner = Callable[[Path, str, str], Awaitable[None] | None]


def pipeline_command(canonical_id: str) -> list[str]:
    return [sys.executable, "-m", "app.ingestion.pipeline", "--resume", "--document-id", canonical_id]


def pipeline_environment(root: Path, collection: str) -> dict[str, str]:
    """The same environment run_rebuild.sh gives the pipeline.

    A separate process because the pipeline's writer fixes its collection at import,
    and because the embedder's memory only comes back when a process exits.
    """
    environment = dict(os.environ)
    environment["QDRANT_GLOBAL_COLLECTION"] = collection
    environment["LEGAL_KB_ROOT"] = str(root)
    environment.setdefault("HF_HUB_OFFLINE", "1")
    environment.setdefault("HF_HOME", str(root / "cache/models"))
    return environment


def run_pipeline_subprocess(root: Path, collection: str, canonical_id: str) -> None:
    result = subprocess.run(
        pipeline_command(canonical_id),
        cwd=BACKEND_ROOT,
        env=pipeline_environment(root, collection),
        check=False,
    )
    if result.returncode != 0:
        raise LifecycleRefused(
            f"The pipeline exited {result.returncode} for {canonical_id}. See its output above."
        )


def _find_document(documents: Iterable[CanonicalDocument], wanted: str) -> CanonicalDocument | None:
    for document in documents:
        if wanted in {document.canonical_document_id, document.document_id}:
            return document
    return None


@dataclass
class AddPlan:
    collection: str
    document: CanonicalDocument
    needs_manifest_row: bool
    already_indexed: bool
    points: int
    same_content_as: list[str] = field(default_factory=list)

    def describe(self) -> list[str]:
        cid = self.document.canonical_document_id
        lines = [f"add {cid} to {self.collection}", f"  {self.document.title}"]
        if self.needs_manifest_row:
            lines.append(f"  append a manifest row ({self.document.document_id})")
        if self.already_indexed:
            lines.append(f"  already indexed: {self.points} point(s), nothing to run")
        else:
            lines.append(f"  run the pipeline on it ({self.points} point(s) there now)")
            lines.append("  confirm the ledger and the point count agree")
        if self.same_content_as:
            lines.append(
                "  warning: the manifest already holds this checksum under "
                + ", ".join(self.same_content_as)
            )
        return lines


async def confirmed_points(root: Path, collection: str, document: CanonicalDocument, client: Any) -> int:
    """How many points prove this document is in, or a refusal saying what is wrong.

    The pipeline exiting zero is not enough. It selects nothing and exits zero when an
    id does not match, and its ledger alone says nothing about the vector store.
    """
    cid = document.canonical_document_id
    entry = _read_ledger(root, collection)["completed"].get(cid)
    if not entry:
        failure = _read_ledger(root, collection)["failed"].get(cid)
        detail = f": {failure.get('error')}" if failure else ""
        raise LifecycleRefused(f"{cid} is not marked complete in the {collection} ledger{detail}")
    if entry.get("sha256") != document.sha256:
        raise LifecycleRefused(f"The {collection} ledger holds a different file for {cid}.")
    expected = int(entry.get("chunk_count") or 0)
    points = await count_document_points(client, collection, cid)
    if expected <= 0 or points != expected:
        raise LifecycleRefused(
            f"{cid}: the ledger records {expected} chunks and {collection} holds {points} points."
        )
    return points


async def plan_add(
    root: Path,
    collection: str,
    wanted: str,
    client: Any,
    *,
    from_manifest: Path | None = None,
) -> AddPlan:
    await _require_collection(client, collection)
    manifest = load_manifest(root / MANIFEST_RELATIVE)
    document = _find_document(manifest, wanted)
    needs_row = False
    if document is None and from_manifest is not None:
        document = _find_document(load_manifest(from_manifest), wanted)
        needs_row = document is not None
    if document is None:
        where = f"{root / MANIFEST_RELATIVE}" + (f" or {from_manifest}" if from_manifest else "")
        raise LifecycleRefused(f"{wanted} is not in {where}.")

    path = root / document.local_path
    if not path.is_file():
        raise LifecycleRefused(f"The source file is not on disk: {path}")
    try:
        verify_document_checksum(document, root)
    except ValueError as exc:
        raise LifecycleRefused(str(exc)) from exc

    entry = _read_ledger(root, collection)["completed"].get(document.canonical_document_id)
    points = await count_document_points(client, collection, document.canonical_document_id)
    return AddPlan(
        collection=collection,
        document=document,
        needs_manifest_row=needs_row,
        already_indexed=bool(
            entry
            and entry.get("sha256") == document.sha256
            and points == int(entry.get("chunk_count") or 0)
            and points > 0
        ),
        points=points,
        same_content_as=sorted(
            {
                item.canonical_document_id
                for item in manifest
                if item.sha256 == document.sha256
                and item.canonical_document_id != document.canonical_document_id
            }
        ),
    )


async def _call_runner(runner: PipelineRunner, root: Path, collection: str, canonical_id: str) -> None:
    outcome = runner(root, collection, canonical_id)
    if outcome is not None:
        await outcome


async def execute_add(
    root: Path,
    collection: str,
    wanted: str,
    client: Any,
    *,
    from_manifest: Path | None = None,
    runner: PipelineRunner = run_pipeline_subprocess,
    lister: Callable[[], list[IngestionProcess]] = list_ingestion_processes,
) -> dict[str, Any]:
    with _manifest_lock(root):
        _refuse_if_ingesting(root, collection, lister)
        plan = await plan_add(root, collection, wanted, client, from_manifest=from_manifest)
        document = plan.document
        cid = document.canonical_document_id
        if plan.needs_manifest_row:
            _append_manifest_row(root, document.model_dump(mode="json", exclude_none=True))
        if not plan.already_indexed:
            await _call_runner(runner, root, collection, cid)
        points = await confirmed_points(root, collection, document, client)
        result = {
            "action": "add",
            "collection": collection,
            DOCUMENT_KEY: cid,
            "points": points,
            "manifest_row_added": plan.needs_manifest_row,
        }
        _log(root, result)
        return result


def pending_documents(root: Path, collection: str) -> list[CanonicalDocument]:
    """Canonical documents in the manifest this collection has not completed."""
    completed = _read_ledger(root, collection)["completed"]
    return [
        document
        for document in iter_canonical_documents(load_manifest(root / MANIFEST_RELATIVE))
        if completed.get(document.canonical_document_id, {}).get("sha256") != document.sha256
    ]


# -------------------------------------------------------------------- replace


async def plan_replace(
    root: Path,
    collection: str,
    old_id: str,
    new_id: str,
    client: Any,
    *,
    from_manifest: Path | None = None,
) -> tuple[AddPlan, RetirePlan]:
    add = await plan_add(root, collection, new_id, client, from_manifest=from_manifest)
    if add.document.canonical_document_id == old_id:
        raise LifecycleRefused("The new and old documents are the same document.")
    retire = await plan_retire(root, collection, old_id, client)
    if retire.nothing_to_do:
        raise LifecycleRefused(
            f"{old_id} is not in the manifest, the ledger or {collection}. "
            "Check the id, or use add if there is nothing to replace."
        )
    return add, retire


async def execute_replace(
    root: Path,
    collection: str,
    old_id: str,
    new_id: str,
    client: Any,
    *,
    from_manifest: Path | None = None,
    runner: PipelineRunner = run_pipeline_subprocess,
    lister: Callable[[], list[IngestionProcess]] = list_ingestion_processes,
) -> dict[str, Any]:
    """Retire the old copy only once the new one is confirmed indexed.

    `execute_add` raises on anything short of that confirmation, which leaves the old
    copy serving. Answering from two copies for a moment beats answering from neither.
    """
    await plan_replace(root, collection, old_id, new_id, client, from_manifest=from_manifest)
    added = await execute_add(
        root, collection, new_id, client, from_manifest=from_manifest, runner=runner, lister=lister
    )
    retired = await execute_retire(root, collection, old_id, client, lister=lister)
    return {"action": "replace", "added": added, "retired": retired}
