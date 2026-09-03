"""Configuration must not depend on where the process was launched.

`env_file=".env"` is resolved against the working directory. The backend run
from the repository root and the same backend run from backend/ therefore
loaded two different configurations, and the second silently fell back to the
development credential defaults -- which failed against real services with
"InvalidAccessKeyId" rather than with a missing-configuration error.

Silent divergence is the failure mode worth a test here: a loud one would have
been found the first time anyone ran it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.config import _REPOSITORY_ROOT, Settings


def test_the_repository_root_is_where_the_env_file_lives() -> None:
    assert (_REPOSITORY_ROOT / ".env.example").is_file(), (
        f"_REPOSITORY_ROOT resolved to {_REPOSITORY_ROOT}, which does not look "
        "like the repository root"
    )


@pytest.mark.parametrize("subdirectory", [".", "backend", "backend/app", "scripts"])
def test_settings_are_the_same_from_any_working_directory(
    monkeypatch: pytest.MonkeyPatch, subdirectory: str
) -> None:
    target = _REPOSITORY_ROOT / subdirectory
    if not target.is_dir():
        pytest.skip(f"{subdirectory} is not present in this checkout")

    # Process environment beats the env file, so clear the few variables a
    # developer's shell may export. Otherwise every directory agrees for the
    # wrong reason and the test proves nothing.
    for name in ("QDRANT_URL", "S3_ENDPOINT_URL", "OLLAMA_BASE_URL", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.chdir(_REPOSITORY_ROOT)
    from_root = Settings()
    monkeypatch.chdir(target)
    from_subdirectory = Settings()

    assert from_subdirectory.qdrant_url == from_root.qdrant_url
    assert from_subdirectory.s3_endpoint_url == from_root.s3_endpoint_url
    assert from_subdirectory.ollama_base_url == from_root.ollama_base_url
    assert (
        from_subdirectory.s3_access_key_id.get_secret_value()
        == from_root.s3_access_key_id.get_secret_value()
    )


def test_a_developer_shell_can_still_override_the_env_file() -> None:
    """Anchoring the file must not stop an explicit export winning.

    The native backend is started with its own endpoints exported; if the file
    began to outrank them it would be pointed at the compose network.
    """
    original = os.environ.get("QDRANT_URL")
    os.environ["QDRANT_URL"] = "http://example.invalid:6333"
    try:
        assert Settings().qdrant_url == "http://example.invalid:6333"
    finally:
        if original is None:
            os.environ.pop("QDRANT_URL", None)
        else:
            os.environ["QDRANT_URL"] = original


def test_the_env_file_describes_the_host_not_the_compose_network() -> None:
    """.env is read by natively-run processes, so its addresses must resolve
    on this machine. The compose file pins the service-internal names itself."""
    env_file = _REPOSITORY_ROOT / ".env.example"
    compose_only_hosts = ("//qdrant:", "//minio:", "//postgres:")
    body = env_file.read_text(encoding="utf-8")
    offenders = [
        line
        for line in body.splitlines()
        if not line.lstrip().startswith("#")
        and any(host in line for host in compose_only_hosts)
    ]
    assert not offenders, (
        "these env entries name hosts that only resolve inside the compose "
        f"network: {offenders}"
    )


def test_the_compose_file_pins_its_internal_endpoints() -> None:
    """If compose read these from .env, the host-facing values above would be
    passed into the containers and break them."""
    compose = (_REPOSITORY_ROOT / "docker" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    for line in ("QDRANT_URL: http://qdrant:6333", "S3_ENDPOINT_URL: http://minio:9000"):
        assert line in compose, f"compose no longer pins {line!r}"
