"""CORP-05: which Acts to keep checking, and what a check found.

The watch list is derived, never typed in: it holds Acts the curated currency table
or the repeal table names, Acts whose own title says they amend, and Acts whose
manifest note asks for amendments to be verified. Nothing here adds to the record of
what the law is. A finding says two of this project's own files disagree, and a
person decides what that means.

The check needs no network and no database. It compares the local source lists
against the manifest and a stored record, and writes a report for the admin console.
A network pass is optional and off by default. It sends HEAD requests only, to hosts
already in the source lists, with a timeout, and a host that refuses is left alone.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import tempfile
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.dedup import sha256_file
from app.ingestion.metadata import CanonicalDocument, iter_canonical_documents, load_manifest
from app.ingestion.supersession import replacement_for
from app.models import AuditLog, User
from app.models.corpus_lifecycle import AmendmentFindingReview
from app.services.currency import CurrencyDecision, CurrencyStatus, resolve_currency

STATE_RELATIVE = Path("logs/amendment_watch_state.json")
REPORT_RELATIVE = Path("logs/amendment_findings.json")
CURRENCY_TABLE_RELATIVE = Path("metadata/currency_status.json")
REVIEW_OVERDUE_DAYS = 180
OFFICIAL_SUFFIXES = (".gov.in", ".nic.in")
USER_AGENT = "Corpusil-Amendment-Watch/1.0 (+research; official sources only)"
_ASKS_TO_VERIFY = re.compile(r"verify[^.]*\bamendment", re.I)
_AMENDING_TITLE = re.compile(r"\(amendment\)|\bamendment act\b", re.I)
_ACT_SOURCE_TYPES = {"act", "amendment_act"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalise(title: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").casefold()).strip()


def _document_currency(document: CanonicalDocument) -> CurrencyDecision:
    return resolve_currency(
        {
            "act_name": document.act_name,
            "title": document.title,
            "superseded_by": document.superseded_by,
            "is_superseded": True if document.is_superseded else None,
            "is_current": True if document.is_current else None,
        }
    )


@dataclass(frozen=True)
class WatchEntry:
    document: CanonicalDocument
    reasons: tuple[str, ...]
    decision: CurrencyDecision


def watch_reasons(document: CanonicalDocument, decision: CurrencyDecision) -> list[str]:
    reasons: list[str] = []
    if decision.source == "curated":
        reasons.append("curated_supersession" if decision.is_superseded else "curated_in_force")
    if replacement_for(document.act_name, document.title) is not None:
        reasons.append("repeal_table")
    if document.superseded_by or document.supersedes:
        reasons.append("manifest_supersession")
    if _AMENDING_TITLE.search(document.title or "") or _AMENDING_TITLE.search(document.act_name or ""):
        reasons.append("amending_act")
    if _ASKS_TO_VERIFY.search(document.currency_note or ""):
        reasons.append("note_asks_to_verify_amendments")
    return reasons


def build_watch_list(root: Path) -> list[WatchEntry]:
    entries: list[WatchEntry] = []
    for document in iter_canonical_documents(load_manifest(root / "metadata/canonical_documents.jsonl")):
        if document.source_type not in _ACT_SOURCE_TYPES:
            continue
        decision = _document_currency(document)
        reasons = watch_reasons(document, decision)
        if reasons:
            entries.append(WatchEntry(document, tuple(reasons), decision))
    return entries


# --------------------------------------------------------------- source lists


@dataclass(frozen=True)
class LocalSource:
    title: str
    url: str
    filename: str
    current_as_of: str | None
    legal_status: str | None
    sha256: str | None
    listed_in: str


def load_source_lists(directory: Path) -> list[LocalSource]:
    sources: list[LocalSource] = []
    for path in sorted(directory.glob("*.json")):
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("url") and row.get("title"):
                sources.append(
                    LocalSource(
                        title=str(row["title"]),
                        url=str(row["url"]),
                        filename=str(row.get("filename") or ""),
                        current_as_of=row.get("current_as_of"),
                        legal_status=row.get("legal_status"),
                        sha256=row.get("sha256"),
                        listed_in=path.name,
                    )
                )
    return sources


def official_hosts(sources: list[LocalSource]) -> set[str]:
    """Hosts already in the source lists that are recognisably the government's."""
    hosts = {urlsplit(source.url).hostname or "" for source in sources}
    return {host for host in hosts if host.endswith(OFFICIAL_SUFFIXES)}


@dataclass
class _SourceIndex:
    by_url: dict[str, list[LocalSource]] = field(default_factory=dict)
    by_filename: dict[str, list[LocalSource]] = field(default_factory=dict)
    by_title: dict[str, list[LocalSource]] = field(default_factory=dict)

    @classmethod
    def build(cls, sources: list[LocalSource]) -> "_SourceIndex":
        index = cls()
        for source in sources:
            index.by_url.setdefault(source.url, []).append(source)
            if source.filename:
                index.by_filename.setdefault(source.filename, []).append(source)
            index.by_title.setdefault(_normalise(source.title), []).append(source)
        return index

    def matching(self, document: CanonicalDocument) -> list[LocalSource]:
        """The most exact match that exists. A title match can be another edition."""
        return (
            self.by_url.get(document.source_url or "")
            or self.by_filename.get(document.original_filename)
            or self.by_title.get(_normalise(document.title))
            or []
        )


# ------------------------------------------------------------------- findings


def _finding(kind: str, *, title: str, detail: str, observed: str, watch_id: str, **extra: Any) -> dict[str, Any]:
    identity = f"{watch_id}|{kind}|{observed}"
    return {
        "id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32],
        "kind": kind,
        "watch_id": watch_id,
        "title": title,
        "detail": detail,
        "observed": observed,
        **extra,
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _source_says_repealed(status: str | None) -> bool:
    return "REPEALED" in (status or "").upper()


def _check_entry(
    entry: WatchEntry,
    sources: list[LocalSource],
    record: dict[str, Any],
    candidates_dir: Path | None,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """Findings for one watched Act, its new record, and how far it could be checked."""
    document = entry.document
    watch_id = document.canonical_document_id
    findings: list[dict[str, Any]] = []
    updated: dict[str, Any] = {"manifest_sha256": document.sha256}

    recorded_sha = record.get("manifest_sha256")
    if recorded_sha and recorded_sha != document.sha256:
        findings.append(
            _finding(
                "manifest_file_changed",
                title=document.title,
                watch_id=watch_id,
                observed=document.sha256,
                recorded=recorded_sha,
                detail="The manifest now records a different file for this document than at the last check.",
            )
        )

    if not sources:
        return findings, updated, "no_local_source"

    newest_date: str | None = None
    for source in sources:
        if source.current_as_of and (newest_date is None or source.current_as_of > newest_date):
            newest_date = source.current_as_of

        # Only a source tied to this exact file can be compared by checksum. A title
        # match may be a different edition, and disagreeing would then mean nothing.
        same_source = source.url == document.source_url or source.filename == document.original_filename
        local_sha = source.sha256 if same_source else None
        if same_source and not local_sha and candidates_dir is not None and source.filename:
            candidate = candidates_dir / source.filename
            if candidate.is_file():
                local_sha = sha256_file(candidate)
        if local_sha and local_sha != document.sha256:
            findings.append(
                _finding(
                    "local_copy_differs",
                    title=document.title,
                    watch_id=watch_id,
                    observed=local_sha,
                    recorded=document.sha256,
                    source=source.url,
                    listed_in=source.listed_in,
                    detail="The local copy of this source has a different checksum from the indexed file.",
                )
            )

        if _source_says_repealed(source.legal_status) and not entry.decision.is_superseded:
            findings.append(
                _finding(
                    "source_list_says_repealed",
                    title=document.title,
                    watch_id=watch_id,
                    observed=str(source.legal_status),
                    recorded=entry.decision.status.value,
                    source=source.url,
                    listed_in=source.listed_in,
                    detail=(
                        f"{source.listed_in} records {source.legal_status}. The currency table "
                        f"resolves this document as {entry.decision.status.value}."
                    ),
                )
            )

    recorded_date = record.get("source_current_as_of")
    if newest_date:
        updated["source_current_as_of"] = newest_date
        if recorded_date and newest_date > recorded_date:
            findings.append(
                _finding(
                    "source_date_newer",
                    title=document.title,
                    watch_id=watch_id,
                    observed=newest_date,
                    recorded=recorded_date,
                    detail=f"A source list now dates this Act {newest_date}, later than the {recorded_date} on record.",
                )
            )
    return findings, updated, "checked"


def _table_findings(root: Path, documents: list[CanonicalDocument], today: date) -> list[dict[str, Any]]:
    path = root / CURRENCY_TABLE_RELATIVE
    table = _read_json(path)
    findings: list[dict[str, Any]] = []
    reviewed_on = table.get("reviewed_on")
    if reviewed_on:
        age = (today - date.fromisoformat(reviewed_on)).days
        if age > REVIEW_OVERDUE_DAYS:
            findings.append(
                _finding(
                    "currency_table_review_overdue",
                    title="Curated currency table",
                    watch_id="currency_status",
                    observed=reviewed_on,
                    detail=f"The table was last reviewed {age} days ago, on {reviewed_on}.",
                )
            )
    titles = {_normalise(document.title) for document in documents} | {
        _normalise(document.act_name) for document in documents
    }
    for row in table.get("entries", []):
        successor = row.get("superseded_by")
        if successor and _normalise(successor) not in titles:
            findings.append(
                _finding(
                    "successor_not_in_corpus",
                    title=str(row.get("starts_with")),
                    watch_id=f"currency:{row.get('starts_with')}",
                    observed=str(successor),
                    detail=f"The currency table names {successor} as the successor. No manifest row has that exact title.",
                )
            )
    return findings


# ---------------------------------------------------------------- optional fetch


class _StayOnOfficialHosts(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed: set[str]) -> None:
        self.allowed = allowed

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if (urlsplit(newurl).hostname or "") not in self.allowed:
            raise urllib.error.URLError(f"redirect left the allowed hosts: {code}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def head_request(url: str, *, allowed: set[str], timeout: float) -> dict[str, str | None]:
    host = urlsplit(url).hostname or ""
    if host not in allowed or urlsplit(url).scheme != "https":
        raise ValueError("not an allowed official host over https")
    opener = urllib.request.build_opener(_StayOnOfficialHosts(allowed))
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    with opener.open(request, timeout=timeout) as response:
        return {
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
            "content_length": response.headers.get("Content-Length"),
        }


def _fetch_pass(
    entries: list[WatchEntry],
    state: dict[str, Any],
    allowed: set[str],
    *,
    limit: int,
    timeout: float,
    requester: Any = head_request,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Check what the host says about each file. A host that refuses is not retried."""
    findings: list[dict[str, Any]] = []
    outcome: Counter[str] = Counter()
    refused: set[str] = set()
    for entry in entries:
        if outcome["requested"] >= limit:
            outcome["not_reached_limit"] += 1
            continue
        document = entry.document
        url = document.source_url or ""
        host = urlsplit(url).hostname or ""
        if host not in allowed or urlsplit(url).scheme != "https":
            outcome["host_not_allowed"] += 1
            continue
        if host in refused:
            outcome["host_refused_earlier"] += 1
            continue
        outcome["requested"] += 1
        try:
            observed = requester(url, allowed=allowed, timeout=timeout)
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError, ValueError):
            # Blocked, rate-limited, down or redirected elsewhere: all reported and left
            # alone. There is no second attempt and no other route to the file.
            refused.add(host)
            outcome["refused_or_unreachable"] += 1
            continue
        outcome["answered"] += 1
        record = state.setdefault(document.canonical_document_id, {})
        previous = record.get("remote")
        record["remote"] = observed
        if not previous:
            continue
        changed = {
            key: (previous.get(key), value)
            for key, value in observed.items()
            if value and previous.get(key) and previous.get(key) != value
        }
        if changed:
            findings.append(
                _finding(
                    "remote_headers_changed",
                    title=document.title,
                    watch_id=document.canonical_document_id,
                    observed=json.dumps(observed, sort_keys=True),
                    source=url,
                    detail="The host reports this file has changed since the last check: "
                    + ", ".join(sorted(changed)),
                )
            )
    return findings, outcome


# ------------------------------------------------------------------- the check


def run_check(
    root: Path,
    sources_dir: Path,
    *,
    output_root: Path | None = None,
    candidates_dir: Path | None = None,
    fetch: bool = False,
    fetch_limit: int = 25,
    timeout: float = 15.0,
    now: datetime | None = None,
    requester: Any = head_request,
) -> dict[str, Any]:
    """Compare, record and report. Writes under `output_root`, never to the manifest."""
    current = now or _utcnow()
    out = output_root or root
    state_path = out / STATE_RELATIVE
    report_path = out / REPORT_RELATIVE
    state = _read_json(state_path)
    previous_report = _read_json(report_path)
    first_seen = {item["id"]: item.get("first_seen") for item in previous_report.get("findings", [])}

    documents = list(iter_canonical_documents(load_manifest(root / "metadata/canonical_documents.jsonl")))
    entries = build_watch_list(root)
    sources = load_source_lists(sources_dir)
    index = _SourceIndex.build(sources)
    checked_at = current.isoformat()

    findings: list[dict[str, Any]] = []
    coverage: Counter[str] = Counter()
    watch: list[dict[str, Any]] = []
    for entry in entries:
        cid = entry.document.canonical_document_id
        record = state.get(cid, {})
        entry_findings, updated, standing = _check_entry(
            entry, index.matching(entry.document), record, candidates_dir
        )
        findings.extend(entry_findings)
        coverage[standing] += 1
        state[cid] = {
            **record,
            **updated,
            "title": entry.document.title,
            "last_checked": checked_at if standing == "checked" else record.get("last_checked"),
        }
        watch.append(
            {
                "watch_id": cid,
                "title": entry.document.title,
                "reasons": list(entry.reasons),
                "currency": entry.decision.status.value,
                "superseded_by": entry.decision.superseded_by,
                "standing": standing,
                "last_checked": state[cid]["last_checked"],
                "source_url": entry.document.source_url,
            }
        )
    findings.extend(_table_findings(root, documents, current.date()))

    fetch_outcome: Counter[str] = Counter()
    if fetch:
        fetch_findings, fetch_outcome = _fetch_pass(
            entries, state, official_hosts(sources), limit=fetch_limit, timeout=timeout, requester=requester
        )
        findings.extend(fetch_findings)

    unique = {item["id"]: item for item in findings}
    for finding_id, item in unique.items():
        item["first_seen"] = first_seen.get(finding_id) or checked_at

    report = {
        "checked_at": checked_at,
        "mode": "network" if fetch else "offline",
        "watched": len(entries),
        "coverage": dict(coverage),
        "source_entries": len(sources),
        "fetch": dict(fetch_outcome),
        "findings": sorted(unique.values(), key=lambda item: (item["kind"], item["title"])),
        "watch": sorted(watch, key=lambda item: item["title"]),
    }
    _write_json(state_path, state)
    _write_json(report_path, report)
    return report


def load_report(root: Path) -> dict[str, Any] | None:
    report = _read_json(root / REPORT_RELATIVE)
    return report or None


# -------------------------------------------------------------- the admin console


async def console_view(
    session: AsyncSession, root: Path, *, page: int, page_size: int
) -> dict[str, Any]:
    """The last check's findings with their review state, and one page of the watch list."""
    report = load_report(root)
    if report is None:
        return {
            "has_run": False,
            "findings": [],
            "open_findings": 0,
            "watch": [],
            "watch_total": 0,
            "page": page,
            "page_size": page_size,
        }
    reviews = {
        row.finding_id: row
        for row in (await session.scalars(select(AmendmentFindingReview))).all()
    }
    findings = [
        {
            **item,
            "review_status": reviews[item["id"]].status if item["id"] in reviews else "open",
            "review_note": reviews[item["id"]].note if item["id"] in reviews else None,
        }
        for item in report.get("findings", [])
    ]
    watch = report.get("watch", [])
    start = (page - 1) * page_size
    return {
        "has_run": True,
        "checked_at": report.get("checked_at"),
        "mode": report.get("mode"),
        "watched": report.get("watched"),
        "coverage": report.get("coverage", {}),
        "source_entries": report.get("source_entries"),
        "fetch": report.get("fetch", {}),
        # Open first, so the ones that need a person are at the top.
        "findings": sorted(findings, key=lambda item: item["review_status"] != "open"),
        "open_findings": sum(1 for item in findings if item["review_status"] == "open"),
        "watch": watch[start : start + page_size],
        "watch_total": len(watch),
        "page": page,
        "page_size": page_size,
    }


async def review_finding(
    session: AsyncSession, root: Path, *, admin: User, finding_id: str, status: str, note: str | None
) -> dict[str, Any]:
    report = load_report(root) or {}
    if not any(item["id"] == finding_id for item in report.get("findings", [])):
        raise HTTPException(status_code=404, detail="Finding not found in the latest check")
    row = await session.get(AmendmentFindingReview, finding_id)
    if row is None:
        row = AmendmentFindingReview(finding_id=finding_id, status=status)
        session.add(row)
    row.status = status
    row.note = note.strip() or None if note else None
    row.reviewed_by = admin.id
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.amendment_finding.reviewed",
            resource_type="amendment_finding",
            metadata_={"finding_id": finding_id, "status": status, "has_note": bool(row.note)},
        )
    )
    await session.commit()
    return {"id": finding_id, "review_status": row.status, "review_note": row.note}
