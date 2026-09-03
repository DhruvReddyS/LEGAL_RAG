from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_explicit_cors_origins_are_normalized_and_deduplicated() -> None:
    settings = Settings(
        _env_file=None,
        cors_origins="https://app.example.test, https://api.example.test,https://app.example.test",
    )
    assert settings.cors_origin_list == [
        "https://app.example.test",
        "https://api.example.test",
    ]


def test_wildcard_cors_is_rejected_for_cookie_authentication() -> None:
    with pytest.raises(ValidationError, match="wildcard CORS is forbidden"):
        Settings(_env_file=None, cors_origins="*")


@pytest.mark.parametrize(
    "origin",
    [
        "https://user:password@app.example.test",
        "https://app.example.test/path",
        "file:///tmp/app.html",
        "tauri://remote-host",
    ],
)
def test_malformed_or_unsafe_cors_origins_are_rejected(origin: str) -> None:
    with pytest.raises(ValidationError, match="CORS origin|Tauri origin"):
        Settings(_env_file=None, cors_origins=origin)


def test_cookie_security_defaults_follow_environment_and_allow_override(monkeypatch) -> None:
    # Settings reads env vars ahead of its defaults, so an exported
    # COOKIE_SECURE from a local .env would silently answer for the assertion
    # this test is making about the default.
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    assert Settings(_env_file=None, app_env="development").auth_cookie_secure is False
    assert Settings(_env_file=None, app_env="production").auth_cookie_secure is True
    assert (
        Settings(_env_file=None, app_env="development", cookie_secure=True).auth_cookie_secure
        is True
    )


def test_cross_site_cookie_mode_requires_secure_transport(monkeypatch) -> None:
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    with pytest.raises(ValidationError, match="COOKIE_SAMESITE=none requires"):
        Settings(
            _env_file=None,
            app_env="development",
            cookie_secure=False,
            cookie_samesite="none",
        )


def test_insecure_cookie_override_is_rejected_outside_development(monkeypatch) -> None:
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    with pytest.raises(ValidationError, match="secure authentication cookies"):
        Settings(_env_file=None, app_env="production", cookie_secure=False)


def test_trusted_hosts_are_explicit_and_deduplicated() -> None:
    settings = Settings(
        _env_file=None,
        trusted_hosts="localhost, host.tailnet.ts.net,localhost",
    )
    assert settings.trusted_host_list == ["localhost", "host.tailnet.ts.net"]

    with pytest.raises(ValidationError, match="invalid trusted host"):
        Settings(_env_file=None, trusted_hosts="*")


def _compose_defaults() -> dict[str, str]:
    """Extract `${VAR:-default}` values from the backend service environment."""
    compose = (
        Path(__file__).resolve().parents[2] / "docker" / "docker-compose.yml"
    ).read_text(encoding="utf-8")
    return dict(re.findall(r"^\s+([A-Z0-9_]+): \$\{[A-Z0-9_]+:-(.+?)\}$", compose, re.M))


def test_compose_inference_defaults_match_application_defaults() -> None:
    """A clone that runs compose without .env must use the benchmarked model.

    The compose default previously named a different model than config.py, so
    a default run silently used a model no recorded measurement was taken
    against.
    """
    defaults = _compose_defaults()
    settings = Settings(_env_file=None)

    assert defaults["OLLAMA_MODEL"] == settings.ollama_model
    assert defaults["EMBEDDING_MODEL"] == settings.embedding_model
    assert int(defaults["EMBEDDING_DIMENSION"]) == settings.embedding_dimension
    assert defaults["QDRANT_DENSE_VECTOR_NAME"] == settings.qdrant_dense_vector_name
    assert defaults["QDRANT_SPARSE_VECTOR_NAME"] == settings.qdrant_sparse_vector_name


def test_container_healthchecks_probe_readiness_not_liveness() -> None:
    """A liveness probe reports healthy while Qdrant is unreachable."""
    root = Path(__file__).resolve().parents[2]
    for relative in ("docker/docker-compose.yml", "docker/Dockerfile.backend"):
        content = (root / relative).read_text(encoding="utf-8")
        assert "127.0.0.1:8000/health/ready" in content, relative
        assert "127.0.0.1:8000/health'" not in content, relative


def test_accelerated_inference_is_opt_in() -> None:
    assert Settings(_env_file=None).expect_accelerated_inference is False
    assert (
        Settings(_env_file=None, expect_accelerated_inference=True).expect_accelerated_inference
        is True
    )
