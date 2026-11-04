"""The release console: gate results, cutover decisions, and the gate queue.

Evidence is read from docs/evidence/gates/<label>/, the directory the gate suite
writes to. Nothing here runs a gate. The suite needs an idle machine and its own
API on port 8000, so it cannot run inside the process serving this request: the
console queues a run, and scripts/run_queued_gates.py executes it.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AuditLog, User
from app.models.admin_tools import GateRun, ReleaseDecision
from app.services.admin_evidence import evidence_root

LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
COLLECTION_RE = re.compile(r"^global_legal_corpus(_[a-z0-9]+)*$")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_READABLE_SUFFIXES = {".txt", ".md"}
_MAX_READ_BYTES = 256 * 1024
_EXCERPT_LINES = 24

# The same patterns the gate script refuses on.
_REBUILD_PROCESSES = (
    "app.ingestion.pipeline",
    "rebuild_until_done.sh __loop",
    "scripts/run_rebuild.sh",
)


@dataclass(frozen=True)
class GateSpec:
    key: str
    name: str
    checks: str
    output: str
    # Left by the evaluation before its gate check runs. Present without the
    # gate's output, it means the run stopped part-way, which is not "not run".
    progress: str | None = None


GATES: tuple[GateSpec, ...] = (
    GateSpec("payload", "Payload", "Manifest fields that must reach the index", "payload.txt"),
    GateSpec(
        "retrieval",
        "Retrieval quality",
        "Recall and citation accuracy against the recorded baseline",
        "retrieval-gate.txt",
        "retrieval-eval.log",
    ),
    GateSpec(
        "answers",
        "Answers",
        "Abstention, ground coverage, unsupported claims",
        "answer-gate.txt",
        "answer-eval.log",
    ),
    GateSpec("provision", "Provision reach", "Whether the governing provision can be reached", "provision.txt"),
    GateSpec("health", "Retrieval health", "Index and configuration checks", "health.txt"),
    GateSpec("latency", "Latency", "Fast p95, Deep overhead, time to first useful output", "latency-gate.txt"),
    GateSpec("provisions", "Provision drift", "Hardcoded statutory citations still resolve", "provision-drift.txt"),
)

_FAIL_MARKERS = re.compile(r"\bFAILED\b|\bREGRESSION\b|UNSUPPORTED CLAIMS|evaluation itself failed|did not become ready")
_PASS_MARKERS = re.compile(r"gate passed|no provision became unreachable", re.IGNORECASE)
_SKIP_MARKERS = re.compile(r"already holds port 8000|no baseline at")
_HEALTH_TOTALS = re.compile(r"(\d+) passed, (\d+) failed, (\d+) blocked")
_SUMMARY_ROW = re.compile(r"^\|\s*([a-z]+)(?: \(exit \d+\))?\s*\|\s*(\*\*FAILED\*\*|passed|skipped)\s*\|", re.M)


def gate_root() -> Path:
    if settings.gate_evidence_root:
        return Path(settings.gate_evidence_root)
    return evidence_root() / "gates"


def status_from_output(text: str) -> str:
    """Read one gate's own output. A failure anywhere outranks a pass line."""
    if _FAIL_MARKERS.search(text):
        return "failed"
    totals = _HEALTH_TOTALS.search(text)
    if totals:
        failed, blocked = int(totals.group(2)), int(totals.group(3))
        if failed:
            return "failed"
        return "incomplete" if blocked else "passed"
    if _SKIP_MARKERS.search(text):
        return "skipped"
    if _PASS_MARKERS.search(text):
        return "passed"
    return "incomplete"


def _safe_read(path: Path) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - _MAX_READ_BYTES))
        return _ANSI.sub("", handle.read().decode("utf-8", errors="replace"))


def _excerpt(text: str) -> str:
    lines = [line for line in text.replace("\r", "\n").splitlines() if line.strip()]
    return "\n".join(lines[-_EXCERPT_LINES:])


def read_gate_evidence(label: str) -> dict[str, Any]:
    """Per-gate results for one label. SUMMARY.md is final when it exists."""
    directory = _label_directory(label)
    summary_path = directory / "SUMMARY.md"
    summary: dict[str, str] = {}
    if summary_path.is_file():
        for name, result in _SUMMARY_ROW.findall(_safe_read(summary_path)):
            summary[name] = "failed" if "FAILED" in result else result

    gates = []
    for spec in GATES:
        output = directory / spec.output
        excerpt = ""
        if output.is_file():
            text = _safe_read(output)
            status = status_from_output(text)
            excerpt = _excerpt(text)
        elif spec.progress and (directory / spec.progress).is_file():
            status = "incomplete"
            excerpt = _excerpt(_safe_read(directory / spec.progress))
        else:
            status = "not_run"
        if spec.key in summary:
            status = summary[spec.key]
        gates.append(
            {
                "key": spec.key,
                "name": spec.name,
                "checks": spec.checks,
                "status": status,
                "excerpt": excerpt,
            }
        )
    counts = {
        name: sum(1 for gate in gates if gate["status"] == name)
        for name in ("passed", "failed", "skipped", "incomplete", "not_run")
    }
    modified = [path.stat().st_mtime for path in directory.iterdir() if path.is_file()]
    return {
        "label": label,
        "gates": gates,
        "counts": counts,
        "all_passed": counts["passed"] == len(GATES),
        "has_summary": bool(summary),
        "updated_at": (
            datetime.fromtimestamp(max(modified), tz=timezone.utc).isoformat() if modified else None
        ),
        "documents": sorted(
            path.name for path in directory.iterdir()
            if path.is_file() and path.suffix in _READABLE_SUFFIXES
        ),
    }


def _label_directory(label: str) -> Path:
    if not LABEL_RE.fullmatch(label):
        raise HTTPException(status_code=422, detail="Not a valid gate label")
    root = gate_root().resolve()
    directory = (root / label).resolve()
    if directory.parent != root or not directory.is_dir():
        raise HTTPException(status_code=404, detail="No gate evidence under this label")
    return directory


def list_labels() -> list[str]:
    root = gate_root()
    if not root.is_dir():
        return []
    return sorted(
        (path.name for path in root.iterdir() if path.is_dir() and LABEL_RE.fullmatch(path.name)),
        key=lambda name: (root / name).stat().st_mtime,
        reverse=True,
    )


def read_gate_document(label: str, name: str) -> str:
    directory = _label_directory(label)
    path = (directory / name).resolve()
    if path.parent != directory or path.suffix not in _READABLE_SUFFIXES or not path.is_file():
        raise HTTPException(status_code=404, detail="No such evidence file")
    return _safe_read(path)


def rebuild_is_running() -> bool:
    for pattern in _REBUILD_PROCESSES:
        try:
            result = subprocess.run(
                ["pgrep", "-f", pattern], capture_output=True, timeout=5, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            # Cannot tell. The gate script checks again before it measures.
            continue
        if result.returncode == 0:
            return True
    return False


async def corpus_collections(client: Any) -> dict[str, Any]:
    """Global collections and their sizes. Read-only, and survives an outage."""
    try:
        listed = await client.get_collections()
        names = sorted(
            item.name for item in listed.collections if COLLECTION_RE.fullmatch(item.name)
        )
        rows = []
        for name in names:
            info = await client.get_collection(name)
            rows.append(
                {
                    "name": name,
                    "points": info.points_count,
                    "status": str(getattr(info.status, "value", info.status)),
                }
            )
        return {"reachable": True, "collections": rows}
    except Exception as exc:  # noqa: BLE001 - the console must still render
        return {"reachable": False, "error_type": type(exc).__name__, "collections": []}


def cutover_steps(collection: str) -> list[dict[str, str]]:
    """How to point the service at a collection.

    `GLOBAL_LEGAL_CORPUS` is resolved when app.ingestion.init_qdrant is imported
    and the retrieval service, workflow and worker hold it for the life of the
    process. Changing it live would leave requests in flight on either side and
    the embedding caches behind them, so this is a restart, and the console
    states it rather than offering a button that would not do what it says.
    """
    return [
        {
            "title": "Set the serving collection",
            "command": f"QDRANT_GLOBAL_COLLECTION={collection}",
            "detail": "Change this line in the deployment's .env file.",
        },
        {
            "title": "Restart the backend",
            "command": "docker compose --env-file .env -f docker/docker-compose.yml up -d backend",
            "detail": "The collection is read once at startup. Nothing changes until this runs.",
        },
        {
            "title": "Confirm it came up",
            "command": "curl -s http://127.0.0.1:8000/health/ready",
            "detail": "Expect status ready, then check the serving collection on this page.",
        },
    ]


async def release_state(session: AsyncSession, client: Any) -> dict[str, Any]:
    labels = await asyncio.to_thread(list_labels)
    evidence = [await asyncio.to_thread(read_gate_evidence, label) for label in labels]
    decisions = (
        await session.execute(
            select(ReleaseDecision, User.name)
            .outerjoin(User, User.id == ReleaseDecision.decided_by)
            .order_by(ReleaseDecision.decided_at.desc())
            .limit(50)
        )
    ).all()
    runs = (
        await session.scalars(select(GateRun).order_by(GateRun.requested_at.desc()).limit(20))
    ).all()
    collections = await corpus_collections(client)
    serving = settings.qdrant_global_collection
    approved = [row for row, _ in decisions if row.decision == "approve"]
    rollback = next((row.collection for row in approved if row.collection != serving), None)
    blockers = await gate_queue_blockers(session)
    return {
        "serving_collection": serving,
        "collections": collections,
        "evidence": evidence,
        "gate_specs": [{"key": spec.key, "name": spec.name, "checks": spec.checks} for spec in GATES],
        "decisions": [_decision(row, name) for row, name in decisions],
        "gate_runs": [_gate_run(run) for run in runs],
        "queue_blockers": blockers,
        "runner_command": "scripts/run_queued_gates.py --once",
        "rollback": (
            {"collection": rollback, "steps": cutover_steps(rollback)} if rollback else None
        ),
        "live_switch_supported": False,
    }


def _decision(row: ReleaseDecision, actor: str | None) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "label": row.label,
        "collection": row.collection,
        "decision": row.decision,
        "reason": row.reason,
        "override_failed_gates": row.override_failed_gates,
        "gate_snapshot": row.gate_snapshot,
        "decided_by": actor,
        "decided_at": row.decided_at.isoformat(),
    }


def _gate_run(run: GateRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "label": run.label,
        "collection": run.collection,
        "status": run.status,
        "exit_code": run.exit_code,
        "requested_at": run.requested_at.isoformat() if run.requested_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


async def record_decision(
    session: AsyncSession,
    *,
    admin: User,
    label: str,
    collection: str,
    decision: str,
    reason: str,
    override_failed_gates: bool,
) -> dict[str, Any]:
    if not COLLECTION_RE.fullmatch(collection):
        raise HTTPException(status_code=422, detail="Not a valid corpus collection name")
    evidence = await asyncio.to_thread(read_gate_evidence, label)
    if decision == "approve" and not evidence["all_passed"] and not override_failed_gates:
        # The suite's own last line is that such a collection must not be
        # promoted. Approving anyway is possible, because a gate can be wrong:
        # the v5 retrieval failure compares against a baseline two generations
        # old. It takes a deliberate act and goes on the record as one.
        raise HTTPException(
            status_code=409,
            detail=(
                "Not every gate has passed. Approving anyway needs an explicit "
                "override and a written reason."
            ),
        )
    snapshot = {
        "counts": evidence["counts"],
        "gates": {gate["key"]: gate["status"] for gate in evidence["gates"]},
    }
    row = ReleaseDecision(
        label=label,
        collection=collection,
        decision=decision,
        reason=reason,
        override_failed_gates=bool(override_failed_gates and not evidence["all_passed"]),
        gate_snapshot=snapshot,
        decided_by=admin.id,
    )
    session.add(row)
    await session.flush()
    session.add(
        AuditLog(
            user_id=admin.id,
            action=f"admin.release.{decision}",
            resource_type="release_decision",
            resource_id=row.id,
            metadata_={
                "label": label,
                "collection": collection,
                "override_failed_gates": row.override_failed_gates,
                "gates": snapshot["gates"],
            },
        )
    )
    await session.commit()
    await session.refresh(row)
    return _decision(row, admin.name)


async def cutover_plan(
    session: AsyncSession, *, admin: User, collection: str, confirm_collection: str
) -> dict[str, Any]:
    if not COLLECTION_RE.fullmatch(collection):
        raise HTTPException(status_code=422, detail="Not a valid corpus collection name")
    if confirm_collection != collection:
        raise HTTPException(
            status_code=422, detail="Type the collection name exactly to confirm the cutover"
        )
    latest = await session.scalar(
        select(ReleaseDecision)
        .where(ReleaseDecision.collection == collection)
        .order_by(ReleaseDecision.decided_at.desc())
        .limit(1)
    )
    if latest is None or latest.decision != "approve":
        raise HTTPException(
            status_code=409, detail="This collection has no standing approval to cut over to"
        )
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.release.cutover_plan",
            resource_type="release_decision",
            resource_id=latest.id,
            metadata_={"collection": collection, "from": settings.qdrant_global_collection},
        )
    )
    await session.commit()
    return {
        "collection": collection,
        "from_collection": settings.qdrant_global_collection,
        "steps": cutover_steps(collection),
        "rollback_steps": cutover_steps(settings.qdrant_global_collection),
        "live_switch_supported": False,
    }


async def gate_queue_blockers(session: AsyncSession) -> list[str]:
    blockers: list[str] = []
    active = await session.scalar(
        select(GateRun).where(GateRun.status.in_(["queued", "running"])).limit(1)
    )
    if active is not None:
        blockers.append(
            f"A gate run for {active.collection} is already {active.status}. "
            "The gates measure an idle machine, so only one can run at a time."
        )
    if await asyncio.to_thread(rebuild_is_running):
        blockers.append(
            "A corpus rebuild is running. A measurement taken while the embedder "
            "and Qdrant are busy is not comparable to one taken idle."
        )
    return blockers


async def queue_gate_run(
    session: AsyncSession,
    *,
    admin: User,
    client: Any,
    label: str,
    collection: str,
) -> dict[str, Any]:
    if not LABEL_RE.fullmatch(label):
        raise HTTPException(status_code=422, detail="Use lowercase letters, digits, dot, dash or underscore")
    if not COLLECTION_RE.fullmatch(collection):
        raise HTTPException(status_code=422, detail="Not a valid corpus collection name")
    blockers = await gate_queue_blockers(session)
    if blockers:
        raise HTTPException(status_code=409, detail=" ".join(blockers))
    known = await corpus_collections(client)
    if known["reachable"] and collection not in {row["name"] for row in known["collections"]}:
        raise HTTPException(status_code=409, detail="This collection does not exist in the vector store")

    run = GateRun(label=label, collection=collection, status="queued", requested_by=admin.id)
    session.add(run)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="A gate run is already queued or running") from exc
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.release.gates_queued",
            resource_type="gate_run",
            resource_id=run.id,
            metadata_={"label": label, "collection": collection},
        )
    )
    await session.commit()
    await session.refresh(run)
    return _gate_run(run)


async def cancel_gate_run(session: AsyncSession, *, admin: User, run_id: uuid.UUID) -> dict[str, Any]:
    run = await session.get(GateRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Gate run not found")
    if run.status != "queued":
        raise HTTPException(status_code=409, detail="Only a run that has not started can be cancelled")
    run.status = "cancelled"
    run.finished_at = datetime.now(timezone.utc)
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.release.gates_cancelled",
            resource_type="gate_run",
            resource_id=run.id,
            metadata_={"label": run.label, "collection": run.collection},
        )
    )
    await session.commit()
    await session.refresh(run)
    return _gate_run(run)


async def claim_next_gate_run(session: AsyncSession) -> GateRun | None:
    """Used by the runner. Atomic, so two runners cannot take one run."""
    run = await session.scalar(
        select(GateRun)
        .where(GateRun.status == "queued")
        .order_by(GateRun.requested_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if run is None:
        return None
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    await session.commit()
    return run


async def finish_gate_run(session: AsyncSession, run_id: uuid.UUID, exit_code: int) -> None:
    await session.execute(
        update(GateRun)
        .where(GateRun.id == run_id)
        .values(
            status="passed" if exit_code == 0 else "failed",
            exit_code=exit_code,
            finished_at=datetime.now(timezone.utc),
        )
    )
    session.add(
        AuditLog(
            user_id=None,
            action="admin.release.gates_finished",
            resource_type="gate_run",
            resource_id=run_id,
            metadata_={"exit_code": exit_code},
        )
    )
    await session.commit()
