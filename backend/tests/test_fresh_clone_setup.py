"""A fresh clone following docs/QUICKSTART_LOCAL.md hit four walls, each fixed at its cause.

The guide named a virtualenv nothing had created. The admin script could not import the
application. Native tools held a database password that did not match the one compose
set, and defaulted to whatever Postgres answered on 5432. The start script gave up
after three minutes while the first run was still downloading its models.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
GUIDE = ROOT / "docs" / "QUICKSTART_LOCAL.md"


def _env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


def test_init_generates_every_secret_and_a_database_url_that_matches(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    shutil.copy(SCRIPTS / "init_local_env.sh", tmp_path / "scripts" / "init_local_env.sh")
    shutil.copy(ROOT / ".env.example", tmp_path / ".env.example")

    done = subprocess.run(
        ["bash", str(tmp_path / "scripts" / "init_local_env.sh")], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr

    values = _env_values(tmp_path / ".env")
    assert "CHANGE_ME" not in (tmp_path / ".env").read_text()
    assert values["POSTGRES_PASSWORD"] != _env_values(ROOT / ".env.example")["POSTGRES_PASSWORD"]
    assert values["DATABASE_URL"] == (
        f"postgresql+asyncpg://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}"
        f"@localhost:{values['POSTGRES_PORT']}/{values['POSTGRES_DB']}"
    )

    # Re-running keeps what is there: these secrets now guard real local data.
    before = (tmp_path / ".env").read_text()
    subprocess.run(["bash", str(tmp_path / "scripts" / "init_local_env.sh")], capture_output=True)
    assert (tmp_path / ".env").read_text() == before


@pytest.mark.parametrize("script", ["create_admin_account.py", "create_professional_account.py"])
def test_the_account_scripts_import_the_application_from_any_directory(script: str, tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, str(SCRIPTS / script), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
    )
    assert done.returncode == 0, done.stderr
    assert "--email" in done.stdout


def test_the_guide_uses_only_what_a_fresh_clone_has() -> None:
    guide = GUIDE.read_text()
    # The admin step runs in the container: the image has to carry the script.
    assert "exec backend" in guide and "python create_admin_account.py" in guide
    assert "create_admin_account.py" in (ROOT / "docker" / "Dockerfile.backend").read_text()
    # A virtualenv is used only after a step that makes it.
    first_use = guide.index(".venv-ingest/bin")
    assert guide.index("python3 -m venv .venv-ingest") < first_use
    # It says plainly that the law is not here.
    assert "What a fresh clone can and cannot do" in guide
    assert "empty" in guide


def test_the_start_script_outwaits_a_first_model_download() -> None:
    script = (SCRIPTS / "start_local.sh").read_text()
    default = re.search(r"STARTUP_WAIT_SECONDS:-(\d+)", script)
    assert default is not None
    assert int(default.group(1)) >= 1200
