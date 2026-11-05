"""Backup and restore: syntax and argument handling only.

Docker here is a stand-in that records being called, placed first on PATH, so
none of this can reach a running stack. What the scripts do to real containers
is not tested by this file.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKUP = ROOT / "scripts" / "backup_local.sh"
RESTORE = ROOT / "scripts" / "restore_local.sh"


@pytest.fixture()
def fake_docker(tmp_path: Path) -> tuple[dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    called = tmp_path / "docker-called"
    script = bin_dir / "docker"
    script.write_text(f'#!/bin/sh\necho "$*" >> "{called}"\nexit 1\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin"}, called


def _run(script: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(script), *args], env=env, capture_output=True, text=True, timeout=30)


def _backup_folder(path: Path, *, tamper: bool = False) -> Path:
    (path / "postgres").mkdir(parents=True)
    (path / "minio").mkdir()
    (path / "qdrant").mkdir()
    (path / "postgres" / "database.dump").write_bytes(b"dump")
    (path / "minio" / "data.tar").write_bytes(b"tar")
    lines = ["# Corpusil backup test"]
    for name in ("minio/data.tar", "postgres/database.dump"):
        digest = hashlib.sha256((path / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    (path / "MANIFEST").write_text("\n".join(lines) + "\n")
    if tamper:
        (path / "minio" / "data.tar").write_bytes(b"changed")
    return path


@pytest.mark.parametrize("script", [BACKUP, RESTORE])
def test_the_syntax_is_valid(script: Path) -> None:
    assert subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True).returncode == 0


@pytest.mark.parametrize("script", [BACKUP, RESTORE])
def test_help_and_unknown_arguments_do_not_reach_docker(script: Path, fake_docker) -> None:
    env, called = fake_docker
    assert _run(script, "--help", env=env).returncode == 0
    assert _run(script, "--nonsense", env=env).returncode == 2
    assert not called.exists()


def test_restore_refuses_without_yes_and_a_folder(fake_docker, tmp_path: Path) -> None:
    env, called = fake_docker
    folder = _backup_folder(tmp_path / "2026-11-05_120000")

    nothing = _run(RESTORE, env=env)
    assert nothing.returncode == 2
    assert "--yes" in nothing.stderr

    no_yes = _run(RESTORE, str(folder), env=env)
    assert no_yes.returncode == 2
    assert "--yes" in no_yes.stderr

    no_folder = _run(RESTORE, "--yes", env=env)
    assert no_folder.returncode == 2
    assert "folder" in no_folder.stderr

    assert not called.exists()


@pytest.mark.parametrize("arguments", [("--yes", "/no/such/folder"), ("--yes", "a", "b")])
def test_restore_refuses_a_bad_folder_argument(fake_docker, arguments) -> None:
    env, called = fake_docker
    assert _run(RESTORE, *arguments, env=env).returncode == 2
    assert not called.exists()


def test_restore_refuses_a_folder_that_is_not_a_finished_backup(fake_docker, tmp_path: Path) -> None:
    env, called = fake_docker
    (tmp_path / "empty").mkdir()
    no_manifest = _run(RESTORE, "--yes", str(tmp_path / "empty"), env=env)
    assert no_manifest.returncode == 2
    assert "MANIFEST" in no_manifest.stderr

    partial = _backup_folder(tmp_path / "2026-11-05_120000.partial")
    assert _run(RESTORE, "--yes", str(partial), env=env).returncode == 2
    assert not called.exists()


def test_restore_changes_nothing_if_the_backup_was_altered(fake_docker, tmp_path: Path) -> None:
    env, called = fake_docker
    folder = _backup_folder(tmp_path / "2026-11-05_120000", tamper=True)
    result = _run(RESTORE, "--yes", str(folder), env=env)
    assert result.returncode == 1
    assert "MANIFEST" in result.stderr
    assert not called.exists()


def test_a_good_backup_passes_its_check_and_only_then_asks_for_docker(fake_docker, tmp_path: Path) -> None:
    env, called = fake_docker
    folder = _backup_folder(tmp_path / "2026-11-05_120000")
    result = _run(RESTORE, "--yes", str(folder), env=env)
    assert "Checking the backup" in result.stdout
    assert result.returncode == 1, "the stand-in Docker reports it is not running"
    if (ROOT / ".env").exists():
        assert called.read_text().startswith("info")


def test_backup_dry_run_names_a_dated_folder_and_touches_nothing(fake_docker, tmp_path: Path) -> None:
    env, called = fake_docker
    dest = tmp_path / "somewhere"
    result = _run(BACKUP, "--dry-run", "--dest", str(dest), env=env)
    assert result.returncode == 0, result.stderr
    assert re.search(rf"{re.escape(str(dest))}/\d{{4}}-\d{{2}}-\d{{2}}_\d{{6}}", result.stdout)
    assert not dest.exists()
    assert not called.exists()


def test_backup_dest_needs_a_value(fake_docker) -> None:
    env, called = fake_docker
    assert _run(BACKUP, "--dest", env=env).returncode == 2
    assert not called.exists()


@pytest.mark.parametrize("script", [BACKUP, RESTORE])
def test_neither_script_reads_secrets_or_uses_a_host_database(script: Path) -> None:
    code = "\n".join(line for line in script.read_text().splitlines() if not line.lstrip().startswith("#"))
    # .env is only ever handed to compose, by path.
    assert not re.search(r"(?:^|\s)(?:source|\.)\s+\S*(?:\.env|ENV_FILE)", code)
    assert not re.search(r"(?:cat|grep|sed|awk)\s+[^|\n]*(?:\.env|ENV_FILE)", code)
    assert "set -x" not in code
    assert "PASSWORD" not in code
    assert "SECRET" not in code
    assert "5432" not in code
    assert "docker compose config" not in code
    assert "pg_dump -h" not in code
