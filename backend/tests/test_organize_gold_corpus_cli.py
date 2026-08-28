from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "organize_gold_corpus.py"
SPEC = importlib.util.spec_from_file_location("organize_gold_corpus", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
organize_gold_corpus = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(organize_gold_corpus)


def make_source_root(tmp_path: Path) -> Path:
    source_root = tmp_path / "source"
    manifests = source_root / "manifests"
    manifests.mkdir(parents=True)
    (manifests / "documents.jsonl").write_text("")
    (manifests / "corpus_summary.json").write_text("{}")
    return source_root


def test_source_root_is_required() -> None:
    with pytest.raises(SystemExit) as error:
        organize_gold_corpus.build_parser().parse_args([])

    assert error.value.code == 2


def test_default_target_is_repository_relative(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_root = make_source_root(tmp_path)
    monkeypatch.chdir(tmp_path)

    args = organize_gold_corpus.build_parser().parse_args(
        ["--source-root", str(source_root)]
    )

    assert args.target_root == REPOSITORY_ROOT / "data" / "legal_kb"


def test_validate_roots_checks_manifest_files(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()

    with pytest.raises(ValueError, match="manifests/documents.jsonl"):
        organize_gold_corpus.validate_roots(source_root, tmp_path / "target")


def test_validate_roots_rejects_target_inside_source(tmp_path: Path) -> None:
    source_root = make_source_root(tmp_path)

    with pytest.raises(ValueError, match="must not overlap"):
        organize_gold_corpus.validate_roots(source_root, source_root / "output")


def test_validate_roots_rejects_source_inside_target(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    source_root = make_source_root(target_root)

    with pytest.raises(ValueError, match="must not overlap"):
        organize_gold_corpus.validate_roots(source_root, target_root)
