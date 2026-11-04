"""Audit F15: the repository is public, so its default secrets are too.

A deployment still using one can have an administrator token forged by anyone
who has read the source.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import Settings

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND.parent / "scripts"
STRONG = "x7Qm2vLp9RtYb4KsN8fHc3WzJ6gUd1Ea5TqPo0Ii"


def _settings(**overrides) -> Settings:
    values = {
        "app_env": "production",
        "cookie_secure": True,
        "jwt_secret_key": STRONG,
        "jwt_refresh_secret_key": STRONG[::-1],
        "s3_access_key_id": "minio-operator",
        "s3_secret_access_key": STRONG,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_strong_secrets_pass() -> None:
    assert _settings().insecure_secrets() == []


@pytest.mark.parametrize(
    ("field", "value", "name"),
    [
        ("jwt_secret_key", "CHANGE_ME", "JWT_SECRET_KEY"),
        ("jwt_secret_key", "development-access-secret-change-me", "JWT_SECRET_KEY"),
        ("jwt_secret_key", "short-secret", "JWT_SECRET_KEY"),
        ("jwt_refresh_secret_key", "CHANGE_ME", "JWT_REFRESH_SECRET_KEY"),
        ("s3_secret_access_key", "CHANGE_ME", "S3_SECRET_ACCESS_KEY"),
        ("s3_secret_access_key", "development-minio-secret", "S3_SECRET_ACCESS_KEY"),
        ("s3_access_key_id", "development-minio-user", "S3_ACCESS_KEY_ID"),
    ],
)
def test_each_weak_secret_is_named(field: str, value: str, name: str) -> None:
    problems = _settings(**{field: value}).insecure_secrets()
    assert len(problems) == 1 and problems[0].startswith(name)
    # This text reaches a startup log.
    assert value not in problems[0]


def test_development_is_left_alone() -> None:
    assert Settings(_env_file=None, app_env="development").insecure_secrets() == []


def _boot(env_overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith(("JWT_", "S3_"))}
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", "from app.core.config import settings; print('started')"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_the_service_will_not_start_in_production_on_public_defaults() -> None:
    result = _boot({"APP_ENV": "production", "COOKIE_SECURE": "true", "JWT_SECRET_KEY": "CHANGE_ME"})
    assert result.returncode != 0
    assert "started" not in result.stdout
    assert "Refusing to start" in result.stderr
    assert "JWT_SECRET_KEY" in result.stderr


def test_the_service_starts_in_production_with_real_secrets() -> None:
    result = _boot(
        {
            "APP_ENV": "production",
            "COOKIE_SECURE": "true",
            "JWT_SECRET_KEY": STRONG,
            "JWT_REFRESH_SECRET_KEY": STRONG[::-1],
            "S3_ACCESS_KEY_ID": "minio-operator",
            "S3_SECRET_ACCESS_KEY": STRONG,
        }
    )
    assert result.returncode == 0, result.stderr
    assert "started" in result.stdout


def _check(env_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPTS / "check_env_secrets.sh"), str(env_file)],
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_the_start_scripts_guard_refuses_change_me(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENV=development\nJWT_SECRET_KEY=CHANGE_ME\nS3_SECRET_ACCESS_KEY=fine-value\n")
    result = _check(env_file)
    assert result.returncode != 0
    assert "JWT_SECRET_KEY" in result.stderr
    assert "S3_SECRET_ACCESS_KEY" not in result.stderr


def test_the_start_scripts_guard_passes_a_filled_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("JWT_SECRET_KEY=abc123\n# JWT_REFRESH_SECRET_KEY=CHANGE_ME in a comment is fine\n")
    assert _check(env_file).returncode == 0


@pytest.mark.parametrize("script", ["start_local.sh", "start_private_demo_host.sh"])
def test_both_start_scripts_call_the_guard(script: str) -> None:
    assert "check_env_secrets.sh" in (SCRIPTS / script).read_text()
