#!/usr/bin/env python3
"""Build the public, read-only Aegis corpus pack for offline installations.

The pack deliberately excludes PostgreSQL, private Qdrant collections, MinIO
objects, authentication secrets, and Ollama models. Those stay per-device.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tarfile
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


COLLECTION = "global_legal_corpus"
PACK_SCHEMA = 1


def request_json(url: str, *, method: str = "GET") -> dict[str, Any]:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def download(url: str, destination: Path) -> None:
    with urllib.request.urlopen(url, timeout=300) as response, destination.open("wb") as target:
        shutil.copyfileobj(response, target, length=1024 * 1024)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_tar_info(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    return info


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--legal-kb-root", type=Path, default=Path("data/legal_kb"))
    parser.add_argument("--output-dir", type=Path, default=Path("dist/offline"))
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Build a small pipeline smoke-test pack without the raw PDFs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    legal_root = args.legal_kb_root.resolve()
    for required in (legal_root / "VERSION", legal_root / "metadata", legal_root / "mapping"):
        if not required.exists():
            raise SystemExit(f"Required corpus path is missing: {required}")

    qdrant_url = args.qdrant_url.rstrip("/")
    qdrant = request_json(f"{qdrant_url}/")
    collection = request_json(f"{qdrant_url}/collections/{COLLECTION}")["result"]
    point_count = int(collection.get("points_count") or 0)
    if point_count <= 0 or collection.get("status") != "green":
        raise SystemExit("The global corpus collection must be green and non-empty.")

    snapshot = request_json(
        f"{qdrant_url}/collections/{COLLECTION}/snapshots", method="POST"
    )["result"]
    snapshot_name = snapshot["name"]
    corpus_version = "-".join(
        line.strip()
        for line in (legal_root / "VERSION").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    version_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", corpus_version).strip("-")
    if not version_slug:
        raise SystemExit("The corpus VERSION file did not contain a usable version.")
    document_rows = [
        json.loads(line)
        for line in (legal_root / "metadata" / "canonical_documents.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    canonical_rows: dict[str, dict[str, Any]] = {}
    for row in document_rows:
        canonical_rows.setdefault(str(row["canonical_document_id"]), row)
    page_count = sum(int(row.get("page_count") or 0) for row in canonical_rows.values())
    suffix = "metadata" if args.metadata_only else "complete"
    pack_name = f"aegis-global-corpus-{version_slug}-{suffix}.tar"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pack_path = args.output_dir.resolve() / pack_name

    with tempfile.TemporaryDirectory(prefix="aegis-corpus-pack-") as temp_name:
        staging = Path(temp_name) / "aegis-global-corpus"
        (staging / "qdrant").mkdir(parents=True)
        snapshot_path = staging / "qdrant" / f"{COLLECTION}.snapshot"
        download(
            f"{qdrant_url}/collections/{COLLECTION}/snapshots/{snapshot_name}",
            snapshot_path,
        )

        for directory in ("metadata", "mapping"):
            shutil.copytree(legal_root / directory, staging / "legal_kb" / directory)
        for filename in ("VERSION", "README.md"):
            source = legal_root / filename
            if source.exists():
                destination = staging / "legal_kb" / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        if not args.metadata_only:
            shutil.copytree(legal_root / "raw", staging / "legal_kb" / "raw")

        files = []
        for path in sorted(item for item in staging.rglob("*") if item.is_file()):
            files.append(
                {
                    "path": path.relative_to(staging).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )

        manifest = {
            "schema": PACK_SCHEMA,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "corpus_version": corpus_version,
            "collection": COLLECTION,
            "qdrant_version": qdrant.get("version"),
            "points": point_count,
            "physical_documents": len(document_rows),
            "canonical_documents": len(canonical_rows),
            "pages": page_count,
            "includes_raw_pdfs": not args.metadata_only,
            "private_data_included": False,
            "files": files,
        }
        (staging / "offline-pack.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        with tarfile.open(pack_path, "w") as archive:
            archive.add(staging, arcname=staging.name, filter=canonical_tar_info)

    checksum = sha256(pack_path)
    checksum_path = pack_path.with_suffix(pack_path.suffix + ".sha256")
    checksum_path.write_text(f"{checksum}  {pack_path.name}\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "pack": str(pack_path),
                "bytes": pack_path.stat().st_size,
                "sha256": checksum,
                "points": point_count,
                "qdrant_version": qdrant.get("version"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
