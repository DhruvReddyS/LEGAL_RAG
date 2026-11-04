"""TOTP against RFC 6238's own vectors, and the helpers around it."""

from __future__ import annotations

import base64

import pytest

from app.core.config import settings
from app.services import totp
from app.services.account_security import describe_device

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()


@pytest.mark.parametrize(
    ("unix_time", "expected"),
    [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1111111111, "14050471"),
        (1234567890, "89005924"),
        (2000000000, "69279037"),
        (20000000000, "65353130"),
    ],
)
def test_rfc_6238_sha1_vectors(unix_time: int, expected: str) -> None:
    assert totp.code_at_step(RFC_SECRET, unix_time // 30, digits=8) == expected


def test_a_code_matches_only_within_one_step_of_drift() -> None:
    now = 1_700_000_000.0
    step = totp.current_step(now)
    secret = totp.generate_secret()
    assert totp.matching_step(secret, totp.code_at_step(secret, step), now=now) == step
    assert totp.matching_step(secret, totp.code_at_step(secret, step - 1), now=now) == step - 1
    assert totp.matching_step(secret, totp.code_at_step(secret, step + 1), now=now) == step + 1
    assert totp.matching_step(secret, totp.code_at_step(secret, step - 2), now=now) is None
    assert totp.matching_step(secret, totp.code_at_step(secret, step + 2), now=now) is None


@pytest.mark.parametrize("code", ["", "12345", "1234567", "abcdef", "١٢٣٤٥٦"])
def test_malformed_codes_never_match(code: str) -> None:
    assert totp.matching_step(totp.generate_secret(), code) is None


def test_a_code_typed_with_a_space_still_matches() -> None:
    now = 1_700_000_000.0
    secret = totp.generate_secret()
    code = totp.code_at_step(secret, totp.current_step(now))
    assert totp.matching_step(secret, f"{code[:3]} {code[3:]}", now=now) is not None


def test_the_stored_form_of_a_secret_is_not_the_secret() -> None:
    secret = totp.generate_secret()
    stored = totp.encrypt_secret(secret)
    assert secret not in stored
    assert totp.decrypt_secret(stored) == secret


def test_a_secret_unreadable_after_a_key_change_is_refused_not_a_crash(monkeypatch) -> None:
    stored = totp.encrypt_secret(totp.generate_secret())
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "mfa_encryption_key", SecretStr("a-completely-different-key-now"))
    assert totp.decrypt_secret(stored) is None
    assert totp.decrypt_secret("not a token") is None


def test_one_time_values_hash_the_same_however_they_are_typed() -> None:
    assert totp.hash_one_time_value("ABCDE-FGHIJ") == totp.hash_one_time_value("abcde fghij")
    assert totp.hash_one_time_value("ABCDE-FGHIJ") != totp.hash_one_time_value("ABCDE-FGHIK")


def test_recovery_codes_are_distinct_and_readable() -> None:
    codes = {totp.generate_recovery_code() for _ in range(50)}
    assert len(codes) == 50
    assert all(len(code) == 11 and code[5] == "-" for code in codes)


def test_the_provisioning_uri_is_what_an_authenticator_expects() -> None:
    uri = totp.provisioning_uri("ABC", "a@example.com", "Corpusil")
    assert uri.startswith("otpauth://totp/Corpusil%3Aa%40example.com?")
    assert "secret=ABC" in uri and "issuer=Corpusil" in uri and "period=30" in uri


@pytest.mark.parametrize(
    ("agent", "origin", "label"),
    [
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15", None, "Safari on macOS"),
        ("Mozilla/5.0 (Windows NT 10.0; Win64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36 Edg/120.0", None, "Edge on Windows"),
        ("Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0", None, "Firefox on Linux"),
        ("Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36", None, "Chrome on Android"),
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) CriOS/120.0 Mobile Safari/604.1", None, "Chrome on iOS"),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15", "tauri://localhost", "Corpusil desktop on macOS"),
        (None, None, "Unknown device"),
        ("curl/8.4.0", None, "Unknown device"),
    ],
)
def test_device_labels(agent, origin, label) -> None:
    assert describe_device(agent, origin=origin) == label
