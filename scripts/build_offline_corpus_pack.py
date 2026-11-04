#!/usr/bin/env python3
"""Build, verify and restore the public, read-only corpus pack for offline installs.

    build_offline_corpus_pack.py build --collection <name> [--output-dir dist/offline]
    build_offline_corpus_pack.py verify <pack.tar>
    build_offline_corpus_pack.py restore <pack.tar> --qdrant-url <url> --legal-kb-root <dir>

The pack deliberately excludes PostgreSQL, private Qdrant collections, MinIO
objects, authentication secrets and Ollama models. Those stay per-device.

Standard library only, so it runs on a machine that has nothing else installed.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACK_SCHEMA = 1
PACK_ROOT = "corpusil-global-corpus"
# Case evidence lives in these. A pack is meant to be handed to other people.
PRIVATE_COLLECTIONS = frozenset({"police_case_data", "advocate_case_data"})
COLLECTION_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class PackError(SystemExit):
    """A refusal with a message for the person running this, and no traceback."""


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


def collection_exists(qdrant_url: str, name: str) -> bool:
    try:
        request_json(f"{qdrant_url}/collections/{urllib.parse.quote(name)}")
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def _version_tuple(version: str | None) -> tuple[int, int]:
    match = re.match(r"v?(\d+)\.(\d+)", version or "")
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


# ------------------------------------------------------------------------ build


def build(args: argparse.Namespace) -> dict[str, Any]:
    collection_name = args.collection
    if not collection_name:
        raise PackError("Name the collection to package with --collection or QDRANT_GLOBAL_COLLECTION.")
    if collection_name in PRIVATE_COLLECTIONS:
        raise PackError(f"{collection_name} holds private case data and must never be packaged.")
    legal_root = args.legal_kb_root.resolve()
    for required in (legal_root / "VERSION", legal_root / "metadata", legal_root / "mapping"):
        if not required.exists():
            raise PackError(f"Required corpus path is missing: {required}")
    if not args.metadata_only and not (legal_root / "raw").exists():
        raise PackError(f"Source PDFs are missing at {legal_root / 'raw'}. Use --metadata-only to leave them out.")

    qdrant_url = args.qdrant_url.rstrip("/")
    qdrant = request_json(f"{qdrant_url}/")
    collection = request_json(f"{qdrant_url}/collections/{collection_name}")["result"]
    point_count = int(collection.get("points_count") or 0)
    if point_count <= 0 or collection.get("status") != "green":
        raise PackError("The global corpus collection must be green and non-empty.")

    corpus_version = "-".join(
        line.strip()
        for line in (legal_root / "VERSION").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    version_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", corpus_version).strip("-")
    if not version_slug:
        raise PackError("The corpus VERSION file did not contain a usable version.")
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
    pack_name = f"corpusil-global-corpus-{version_slug}-{suffix}.tar"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pack_path = args.output_dir.resolve() / pack_name

    snapshot = request_json(f"{qdrant_url}/collections/{collection_name}/snapshots", method="POST")["result"]
    snapshot_name = snapshot["name"]
    try:
        with tempfile.TemporaryDirectory(prefix="corpusil-corpus-pack-", dir=args.output_dir) as temp_name:
            staging = Path(temp_name) / PACK_ROOT
            (staging / "qdrant").mkdir(parents=True)
            snapshot_path = staging / "qdrant" / f"{collection_name}.snapshot"
            download(f"{qdrant_url}/collections/{collection_name}/snapshots/{snapshot_name}", snapshot_path)

            for directory in ("metadata", "mapping"):
                shutil.copytree(legal_root / directory, staging / "legal_kb" / directory)
            for filename in ("VERSION", "README.md"):
                source = legal_root / filename
                if source.exists():
                    shutil.copy2(source, staging / "legal_kb" / filename)
            if not args.metadata_only:
                shutil.copytree(legal_root / "raw", staging / "legal_kb" / "raw")

            files = [
                {
                    "path": path.relative_to(staging).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
                for path in sorted(item for item in staging.rglob("*") if item.is_file())
            ]
            manifest = {
                "schema": PACK_SCHEMA,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "corpus_version": corpus_version,
                "collection": collection_name,
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
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            with tarfile.open(pack_path, "w") as archive:
                archive.add(staging, arcname=staging.name, filter=canonical_tar_info)
    finally:
        # A full copy of the index stays on the server's disk otherwise, once per
        # pack built, until someone notices the disk is full.
        try:
            request_json(
                f"{qdrant_url}/collections/{collection_name}/snapshots/{snapshot_name}", method="DELETE"
            )
        except (urllib.error.URLError, OSError) as exc:
            print(f"Could not remove the snapshot {snapshot_name} from Qdrant: {type(exc).__name__}", file=sys.stderr)

    checksum = sha256(pack_path)
    pack_path.with_suffix(pack_path.suffix + ".sha256").write_text(
        f"{checksum}  {pack_path.name}\n", encoding="utf-8"
    )
    return {
        "pack": str(pack_path),
        "bytes": pack_path.stat().st_size,
        "sha256": checksum,
        "points": point_count,
        "qdrant_version": qdrant.get("version"),
    }


# ----------------------------------------------------------------------- verify


def _safe_extract(pack: Path, target: Path) -> Path:
    """Unpack, refusing anything that would land outside the target.

    A pack may have come from anyone, on a USB stick. Only plain files and
    directories under the expected root are accepted: no links and no `..`.
    """
    with tarfile.open(pack, "r") as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or (path.parts and path.parts[0] != PACK_ROOT):
                raise PackError(f"Refusing a pack with an unsafe path: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise PackError(f"Refusing a pack containing a link or device: {member.name}")
        for member in archive.getmembers():
            destination = target / member.name
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            assert source is not None
            with source, destination.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
    return target / PACK_ROOT


def _check_sidecar(pack: Path) -> None:
    sidecar = pack.with_suffix(pack.suffix + ".sha256")
    if not sidecar.exists():
        return
    expected = sidecar.read_text(encoding="utf-8").split()[0]
    if sha256(pack) != expected:
        raise PackError(f"{pack.name} does not match its .sha256 file. It is damaged or was altered.")


def verify_unpacked(root: Path) -> dict[str, Any]:
    manifest_path = root / "offline-pack.json"
    if not manifest_path.exists():
        raise PackError("This is not a corpus pack: offline-pack.json is missing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != PACK_SCHEMA:
        raise PackError(f"Unsupported pack schema: {manifest.get('schema')}")
    if manifest.get("private_data_included") is not False:
        raise PackError("This pack does not declare itself free of private data.")
    if manifest.get("collection") in PRIVATE_COLLECTIONS:
        raise PackError("This pack contains a private collection.")
    if not COLLECTION_NAME_RE.fullmatch(str(manifest.get("collection"))):
        raise PackError("This pack names an invalid collection.")

    listed = {entry["path"]: entry for entry in manifest["files"]}
    present = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if present != set(listed):
        extra, missing = sorted(present - set(listed)), sorted(set(listed) - present)
        raise PackError(f"Pack contents do not match its manifest. Extra: {extra[:5]} Missing: {missing[:5]}")
    for relative, entry in listed.items():
        if sha256(root / relative) != entry["sha256"]:
            raise PackError(f"Checksum mismatch in {relative}. The pack is damaged or was altered.")
    return manifest


def verify(args: argparse.Namespace) -> dict[str, Any]:
    pack = args.pack.resolve()
    if not pack.exists():
        raise PackError(f"No such pack: {pack}")
    _check_sidecar(pack)
    with tempfile.TemporaryDirectory(prefix="corpusil-pack-verify-") as temp_name:
        manifest = verify_unpacked(_safe_extract(pack, Path(temp_name)))
    return {key: value for key, value in manifest.items() if key != "files"} | {"verified_files": len(manifest["files"])}


# ---------------------------------------------------------------------- restore


def _upload_snapshot(qdrant_url: str, collection: str, snapshot: Path) -> None:
    """Multipart upload, streamed, because a snapshot is many gigabytes."""
    parsed = urllib.parse.urlsplit(qdrant_url)
    boundary = uuid.uuid4().hex
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="snapshot"; filename="{snapshot.name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(parsed.netloc, timeout=3600)
    try:
        connection.putrequest("POST", f"{parsed.path.rstrip('/')}/collections/{collection}/snapshots/upload?wait=true")
        connection.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
        connection.putheader("Content-Length", str(len(head) + snapshot.stat().st_size + len(tail)))
        connection.endheaders()
        connection.send(head)
        with snapshot.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                connection.send(block)
        connection.send(tail)
        response = connection.getresponse()
        body = response.read()
        if response.status >= 300:
            raise PackError(f"Qdrant refused the snapshot ({response.status}): {body[:300].decode(errors='replace')}")
    finally:
        connection.close()


def restore(args: argparse.Namespace) -> dict[str, Any]:
    pack = args.pack.resolve()
    if not pack.exists():
        raise PackError(f"No such pack: {pack}")
    _check_sidecar(pack)
    qdrant_url = args.qdrant_url.rstrip("/")
    legal_root = args.legal_kb_root.resolve()

    with tempfile.TemporaryDirectory(prefix="corpusil-pack-restore-") as temp_name:
        root = _safe_extract(pack, Path(temp_name))
        manifest = verify_unpacked(root)
        source_collection = manifest["collection"]
        collection = args.collection or source_collection
        if collection in PRIVATE_COLLECTIONS or not COLLECTION_NAME_RE.fullmatch(collection):
            raise PackError(f"Refusing to restore into {collection}.")

        server = request_json(f"{qdrant_url}/")
        if _version_tuple(server.get("version")) < _version_tuple(manifest.get("qdrant_version")):
            raise PackError(
                f"This pack was built on Qdrant {manifest.get('qdrant_version')}, and this server runs "
                f"{server.get('version')}. Upgrade the server first."
            )
        if collection_exists(qdrant_url, collection):
            raise PackError(
                f"Collection {collection} already exists, and restoring would replace it. "
                "Choose another name with --collection."
            )
        existing_version = legal_root / "VERSION"
        pack_version = root / "legal_kb" / "VERSION"
        if existing_version.exists() and not args.replace_metadata:
            if pack_version.exists() and existing_version.read_bytes() != pack_version.read_bytes():
                raise PackError(
                    f"{legal_root} already holds a different corpus version. "
                    "Pass --replace-metadata if you mean to replace its metadata."
                )

        _upload_snapshot(qdrant_url, collection, root / "qdrant" / f"{source_collection}.snapshot")
        restored = request_json(f"{qdrant_url}/collections/{collection}")["result"]
        points = int(restored.get("points_count") or 0)
        if points != int(manifest["points"]):
            raise PackError(f"Restored {points} points where the pack holds {manifest['points']}.")

        legal_root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(root / "legal_kb", legal_root, dirs_exist_ok=True)

    return {
        "collection": collection,
        "points": points,
        "legal_kb_root": str(legal_root),
        "next": f"Set QDRANT_GLOBAL_COLLECTION={collection} in .env and restart the backend.",
    }


# -------------------------------------------------------------------------- cli


def parse_args(argv: list[str]) -> argparse.Namespace:
    # A bare set of options is a build, as it always was.
    if not argv or argv[0] not in {"build", "verify", "restore", "-h", "--help"}:
        argv = ["build", *argv]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    make = commands.add_parser("build", help="Produce a pack from a working installation.")
    make.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    make.add_argument(
        "--collection",
        default=os.getenv("QDRANT_GLOBAL_COLLECTION"),
        help="Qdrant collection to package. There is no default: packaging the wrong index is silent.",
    )
    make.add_argument("--legal-kb-root", type=Path, default=Path("data/legal_kb"))
    make.add_argument("--output-dir", type=Path, default=Path("dist/offline"))
    make.add_argument("--metadata-only", action="store_true", help="Leave out the source PDFs.")
    make.set_defaults(run=build)

    check = commands.add_parser("verify", help="Check a pack's checksums without changing anything.")
    check.add_argument("pack", type=Path)
    check.set_defaults(run=verify)

    load = commands.add_parser("restore", help="Load a verified pack into this installation.")
    load.add_argument("pack", type=Path)
    load.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    load.add_argument("--legal-kb-root", type=Path, default=Path("data/legal_kb"))
    load.add_argument("--collection", help="Restore under this name instead of the pack's own.")
    load.add_argument("--replace-metadata", action="store_true", help="Allow replacing a different corpus version's metadata.")
    load.set_defaults(run=restore)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    print(json.dumps(args.run(args), indent=2))


if __name__ == "__main__":
    main()
