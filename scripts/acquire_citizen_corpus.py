#!/usr/bin/env python3
"""Download and validate candidate citizen-law sources without ingesting them."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


USER_AGENT = "Aegis-Legal-Corpus-Acquisition/1.0 (+research; official sources only)"
PDF_MAGIC = b"%PDF-"
HTML_MARKERS = (b"<!doctype html", b"<html")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_prefix(path: Path, size: int = 512) -> bytes:
    with path.open("rb") as source:
        return source.read(size).lstrip().lower()


def validate_download(source: dict[str, Any], temporary: Path, content_type: str) -> None:
    prefix = file_prefix(temporary)
    expected = source["format"]
    if expected == "pdf" and not prefix.startswith(PDF_MAGIC.lower()):
        temporary.unlink(missing_ok=True)
        raise ValueError(f"expected PDF but received {content_type}")
    if expected == "html" and not any(marker in prefix for marker in HTML_MARKERS):
        temporary.unlink(missing_ok=True)
        raise ValueError(f"expected HTML but received {content_type}")
    if temporary.stat().st_size < int(source.get("minimum_bytes", 512)):
        size = temporary.stat().st_size
        temporary.unlink(missing_ok=True)
        raise ValueError(f"response too small to be a valid document ({size} bytes)")


def download(source: dict[str, Any], destination: Path, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        source["url"],
        headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.5"},
    )
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(request, timeout=timeout) as response, temporary.open("wb") as target:
        shutil.copyfileobj(response, target, length=1024 * 1024)
        content_type = response.headers.get_content_type().lower()
        final_url = response.geturl()

    validate_download(source, temporary, content_type)
    temporary.replace(destination)
    return {
        "bytes": destination.stat().st_size,
        "content_type": content_type,
        "final_url": final_url,
        "sha256": sha256(destination),
    }


def download_with_curl(
    source: dict[str, Any], destination: Path, timeout: int
) -> dict[str, Any]:
    temporary = destination.with_suffix(destination.suffix + ".part")
    result = subprocess.run(
        [
            "curl", "--fail", "--location", "--silent", "--show-error",
            "--max-time", str(timeout), "--user-agent", USER_AGENT,
            "--header", "Accept: application/pdf,text/html;q=0.9,*/*;q=0.5",
            "--output", str(temporary), "--write-out",
            "%{content_type}\n%{url_effective}", source["url"],
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    content_type, final_url = result.stdout.splitlines()[-2:]
    validate_download(source, temporary, content_type.lower())
    temporary.replace(destination)
    return {
        "bytes": destination.stat().st_size,
        "content_type": content_type.lower(),
        "final_url": final_url,
        "sha256": sha256(destination),
    }


def acquire_one(source: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    domain_dir = args.output / source["domain"]
    domain_dir.mkdir(parents=True, exist_ok=True)
    destination = domain_dir / source["filename"]
    temporary = destination.with_suffix(destination.suffix + ".part")
    record = {
        **source,
        "local_path": destination.relative_to(args.output).as_posix(),
        "attempted_at": utc_now(),
        "status": "PENDING",
        "error": "",
        "bytes": "",
        "sha256": "",
        "content_type": "",
        "final_url": "",
    }

    if destination.exists() and not args.force:
        prefix = file_prefix(destination)
        valid_pdf = source["format"] != "pdf" or prefix.startswith(PDF_MAGIC.lower())
        if valid_pdf and destination.stat().st_size >= int(source.get("minimum_bytes", 512)):
            record.update(
                status="EXISTING_VALID",
                bytes=destination.stat().st_size,
                sha256=sha256(destination),
            )
            return record

    for attempt in range(1, args.retries + 1):
        try:
            result = download(source, destination, args.timeout)
            record.update(status="DOWNLOADED", **result)
            return record
        except (OSError, ValueError, urllib.error.URLError) as exc:
            temporary.unlink(missing_ok=True)
            if "CERTIFICATE_VERIFY_FAILED" in str(exc):
                try:
                    result = download_with_curl(source, destination, args.timeout)
                    record.update(status="DOWNLOADED", **result)
                    return record
                except (OSError, ValueError, subprocess.SubprocessError) as curl_exc:
                    temporary.unlink(missing_ok=True)
                    exc = curl_exc
            record["error"] = f"attempt {attempt}/{args.retries}: {exc}"
            if attempt < args.retries:
                time.sleep(min(2**attempt, 8))

    record["status"] = "DOWNLOAD_FAILED"
    return record


def acquire(args: argparse.Namespace) -> int:
    sources = json.loads(args.registry.read_text(encoding="utf-8"))
    if not isinstance(sources, list) or not sources:
        raise ValueError("registry must be a non-empty JSON array")
    args.output.mkdir(parents=True, exist_ok=True)
    records_by_id: dict[str, dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(acquire_one, source, args): source for source in sources}
        for future in as_completed(futures):
            source = futures[future]
            record = future.result()
            records_by_id[source["id"]] = record
            detail = f"{record['bytes']} bytes" if record["bytes"] else record["error"]
            print(f"{record['status'].lower()} {source['id']}: {detail}", flush=True)

    records = [records_by_id[source["id"]] for source in sources]

    log_dir = args.output / "_logs"
    log_dir.mkdir(exist_ok=True)
    fields = [
        "id", "title", "domain", "document_type", "authority", "jurisdiction",
        "language", "legal_status", "current_as_of", "format", "url", "final_url",
        "local_path", "status", "content_type", "bytes", "sha256", "attempted_at",
        "currency_note", "error",
    ]
    with (log_dir / "acquisition_manifest.csv").open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    (log_dir / "acquisition_manifest.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    successful = sum(row["status"] in {"DOWNLOADED", "EXISTING_VALID"} for row in records)
    failed = len(records) - successful
    summary = {
        "generated_at": utc_now(),
        "registry": str(args.registry),
        "output": str(args.output),
        "total": len(records),
        "successful": successful,
        "failed": failed,
        "ingested": False,
        "note": "Candidates require legal currency and extraction review before promotion.",
    }
    (log_dir / "acquisition_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0 if failed == 0 else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("data/source_materials/phase_a_official_sources.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/source_materials/candidate_imports/citizen_law_phase_a"),
    )
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(acquire(parse_args()))
