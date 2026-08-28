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


def test_cookie_security_defaults_follow_environment_and_allow_override() -> None:
    assert Settings(_env_file=None, app_env="development").auth_cookie_secure is False
    assert Settings(_env_file=None, app_env="production").auth_cookie_secure is True
    assert (
        Settings(_env_file=None, app_env="development", cookie_secure=True).auth_cookie_secure
        is True
    )
