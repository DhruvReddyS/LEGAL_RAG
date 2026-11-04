"""PLAT-10: a pack can be built, checked and restored, against a real Qdrant.

Uses its own throwaway collection on the test stack, and never a real corpus.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_offline_corpus_pack.py"
_spec = importlib.util.spec_from_file_location("build_offline_corpus_pack", SCRIPT)
pack_tool = importlib.util.module_from_spec(_spec)
sys.modules["build_offline_corpus_pack"] = pack_tool
_spec.loader.exec_module(pack_tool)

QDRANT = os.environ.get("QDRANT_URL", "http://127.0.0.1:56333")
TEST_PREFIX = "offline_pack_test_"


def _api(method: str, path: str, body: dict | None = None) -> dict:
    request = Request(
        f"{QDRANT}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def _legal_kb(root: Path) -> Path:
    (root / "metadata").mkdir(parents=True)
    (root / "mapping").mkdir()
    (root / "raw").mkdir()
    (root / "VERSION").write_text("TEST_CORPUS\n2026-11-04\n")
    (root / "metadata" / "canonical_documents.jsonl").write_text(
        json.dumps({"canonical_document_id": "a", "page_count": 3}) + "\n"
    )
    (root / "mapping" / "map.json").write_text("{}")
    (root / "raw" / "act.pdf").write_bytes(b"%PDF-1.4 test")
    return root


@pytest.fixture
def collection():
    name = f"{TEST_PREFIX}{uuid.uuid4().hex[:10]}"
    _api("PUT", f"/collections/{name}", {"vectors": {"size": 4, "distance": "Cosine"}})
    _api(
        "PUT",
        f"/collections/{name}/points?wait=true",
        {"points": [{"id": index + 1, "vector": [0.1, 0.2, 0.3, 0.4], "payload": {"n": index}} for index in range(3)]},
    )
    created = [name]
    yield name, created
    for item in created:
        _api("DELETE", f"/collections/{item}")


def _build(tmp_path: Path, name: str, *extra: str) -> Path:
    kb = tmp_path / "kb"
    if not kb.exists():
        _legal_kb(kb)
    pack_tool.main(["build", "--qdrant-url", QDRANT, "--collection", name, "--legal-kb-root", str(kb), "--output-dir", str(tmp_path / "dist"), *extra])
    return next((tmp_path / "dist").glob("*.tar"))


@pytest.mark.integration
def test_build_verify_restore_round_trip(tmp_path: Path, collection, capsys) -> None:
    name, created = collection
    pack = _build(tmp_path, name)
    capsys.readouterr()

    # The server keeps no leftover copy of the index.
    assert _api("GET", f"/collections/{name}/snapshots")["result"] == []

    pack_tool.main(["verify", str(pack)])
    report = json.loads(capsys.readouterr().out)
    assert report["points"] == 3 and report["private_data_included"] is False
    assert report["includes_raw_pdfs"] is True

    restored_name = f"{TEST_PREFIX}{uuid.uuid4().hex[:10]}"
    created.append(restored_name)
    target = tmp_path / "restored_kb"
    pack_tool.main(["restore", str(pack), "--qdrant-url", QDRANT, "--legal-kb-root", str(target), "--collection", restored_name])
    result = json.loads(capsys.readouterr().out)
    assert result["points"] == 3
    assert restored_name in result["next"]
    assert _api("GET", f"/collections/{restored_name}")["result"]["points_count"] == 3
    assert (target / "raw" / "act.pdf").read_bytes() == b"%PDF-1.4 test"
    assert (target / "VERSION").exists()


@pytest.mark.integration
def test_restore_never_overwrites_an_existing_collection(tmp_path: Path, collection) -> None:
    name, _ = collection
    pack = _build(tmp_path, name)
    with pytest.raises(SystemExit, match="already exists"):
        pack_tool.main(["restore", str(pack), "--qdrant-url", QDRANT, "--legal-kb-root", str(tmp_path / "t")])
    assert not (tmp_path / "t").exists()


@pytest.mark.integration
def test_metadata_only_leaves_out_the_pdfs(tmp_path: Path, collection, capsys) -> None:
    name, _ = collection
    pack = _build(tmp_path, name, "--metadata-only")
    capsys.readouterr()
    assert "metadata" in pack.name
    pack_tool.main(["verify", str(pack)])
    assert json.loads(capsys.readouterr().out)["includes_raw_pdfs"] is False
    with tarfile.open(pack) as archive:
        assert not [member for member in archive.getnames() if "/raw/" in member]


@pytest.mark.integration
def test_a_different_corpus_version_is_not_silently_replaced(tmp_path: Path, collection) -> None:
    name, _ = collection
    pack = _build(tmp_path, name)
    target = tmp_path / "other"
    target.mkdir()
    (target / "VERSION").write_text("SOMETHING_ELSE\n")
    fresh = f"{TEST_PREFIX}{uuid.uuid4().hex[:10]}"
    with pytest.raises(SystemExit, match="different corpus version"):
        pack_tool.main(["restore", str(pack), "--qdrant-url", QDRANT, "--legal-kb-root", str(target), "--collection", fresh])
    assert (target / "VERSION").read_text() == "SOMETHING_ELSE\n"


@pytest.mark.parametrize("private", ["police_case_data", "advocate_case_data"])
def test_private_collections_can_never_be_packaged(tmp_path: Path, private: str) -> None:
    with pytest.raises(SystemExit, match="private case data"):
        pack_tool.main(["build", "--collection", private, "--legal-kb-root", str(_legal_kb(tmp_path / "kb"))])


def test_building_needs_a_named_collection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("QDRANT_GLOBAL_COLLECTION", raising=False)
    with pytest.raises(SystemExit, match="--collection"):
        pack_tool.main(["build", "--legal-kb-root", str(_legal_kb(tmp_path / "kb"))])


def _handmade_pack(tmp_path: Path, members: dict[str, bytes], *, manifest: dict | None = None) -> Path:
    path = tmp_path / "made.tar"
    root = pack_tool.PACK_ROOT
    body = manifest if manifest is not None else {
        "schema": 1,
        "collection": "global_test",
        "private_data_included": False,
        "points": 1,
        "files": [
            {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in members.items()
        ],
    }
    with tarfile.open(path, "w") as archive:
        for name, data in {**members, "offline-pack.json": json.dumps(body).encode()}.items():
            info = tarfile.TarInfo(f"{root}/{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return path


def test_a_well_formed_pack_verifies(tmp_path: Path, capsys) -> None:
    pack_tool.main(["verify", str(_handmade_pack(tmp_path, {"legal_kb/VERSION": b"v1"}))])
    assert json.loads(capsys.readouterr().out)["verified_files"] == 1


def test_a_changed_file_fails_verification(tmp_path: Path) -> None:
    manifest = {
        "schema": 1, "collection": "c", "private_data_included": False, "points": 1,
        "files": [{"path": "legal_kb/VERSION", "bytes": 2, "sha256": "0" * 64}],
    }
    with pytest.raises(SystemExit, match="Checksum mismatch"):
        pack_tool.main(["verify", str(_handmade_pack(tmp_path, {"legal_kb/VERSION": b"v1"}, manifest=manifest))])


def test_an_extra_file_fails_verification(tmp_path: Path) -> None:
    manifest = {"schema": 1, "collection": "c", "private_data_included": False, "points": 1, "files": []}
    with pytest.raises(SystemExit, match="do not match"):
        pack_tool.main(["verify", str(_handmade_pack(tmp_path, {"legal_kb/evil": b"x"}, manifest=manifest))])


def test_a_pack_claiming_a_private_collection_is_refused(tmp_path: Path) -> None:
    manifest = {"schema": 1, "collection": "police_case_data", "private_data_included": False, "points": 1, "files": []}
    with pytest.raises(SystemExit, match="private collection"):
        pack_tool.main(["verify", str(_handmade_pack(tmp_path, {}, manifest=manifest))])


def test_a_damaged_tar_fails_against_its_checksum_file(tmp_path: Path) -> None:
    pack = _handmade_pack(tmp_path, {"legal_kb/VERSION": b"v1"})
    pack.with_suffix(".tar.sha256").write_text(f"{'0' * 64}  {pack.name}\n")
    with pytest.raises(SystemExit, match="does not match its .sha256"):
        pack_tool.main(["verify", str(pack)])


@pytest.mark.parametrize("bad_name", [f"{pack_tool.PACK_ROOT}/../../escape.txt", "/etc/escape.txt", "elsewhere/file.txt"])
def test_paths_escaping_the_pack_are_refused(tmp_path: Path, bad_name: str) -> None:
    path = tmp_path / "evil.tar"
    with tarfile.open(path, "w") as archive:
        info = tarfile.TarInfo(bad_name)
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(SystemExit, match="unsafe path"):
        pack_tool.main(["verify", str(path)])
    assert not (tmp_path / "escape.txt").exists()


def test_links_in_a_pack_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "link.tar"
    with tarfile.open(path, "w") as archive:
        info = tarfile.TarInfo(f"{pack_tool.PACK_ROOT}/link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        archive.addfile(info)
    with pytest.raises(SystemExit, match="link or device"):
        pack_tool.main(["verify", str(path)])


def test_it_runs_with_nothing_but_the_standard_library(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "verify", str(tmp_path / "missing.tar")],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "No such pack" in result.stderr
    assert "Traceback" not in result.stderr
