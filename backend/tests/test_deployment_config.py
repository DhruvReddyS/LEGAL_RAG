from __future__ import annotations

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


def test_cookie_security_defaults_follow_environment_and_allow_override() -> None:
    assert Settings(_env_file=None, app_env="development").auth_cookie_secure is False
    assert Settings(_env_file=None, app_env="production").auth_cookie_secure is True
    assert (
        Settings(_env_file=None, app_env="development", cookie_secure=True).auth_cookie_secure
        is True
    )


def test_cross_site_cookie_mode_requires_secure_transport() -> None:
    with pytest.raises(ValidationError, match="COOKIE_SAMESITE=none requires"):
        Settings(
            _env_file=None,
            app_env="development",
            cookie_secure=False,
            cookie_samesite="none",
        )


def test_insecure_cookie_override_is_rejected_outside_development() -> None:
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
