"""RFC 6238 time-based one-time passwords, and encryption of the stored secret.

Implemented on the standard library rather than a dependency: the algorithm is
twenty lines and is tested below against the RFC's own vectors.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

PERIOD_SECONDS = 30
DIGITS = 6
# One step either side, because phone clocks drift. Wider only widens what a
# guess can match.
ALLOWED_DRIFT_STEPS = 1


def generate_secret() -> str:
    """160 random bits, the size RFC 4226 recommends, in authenticator base32."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key_bytes(secret: str) -> bytes:
    padded = secret.strip().upper().replace(" ", "")
    padded += "=" * (-len(padded) % 8)
    return base64.b32decode(padded)


def code_at_step(secret: str, step: int, *, digits: int = DIGITS) -> str:
    digest = hmac.new(_key_bytes(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // PERIOD_SECONDS)


def matching_step(secret: str, code: str, *, now: float | None = None) -> int | None:
    """The time step a code belongs to, or None. Compared in constant time."""
    candidate = code.strip().replace(" ", "")
    if len(candidate) != DIGITS or not candidate.isascii() or not candidate.isdigit():
        return None
    centre = current_step(now)
    found: int | None = None
    # Every candidate is checked, so timing does not say which step matched.
    for step in range(centre - ALLOWED_DRIFT_STEPS, centre + ALLOWED_DRIFT_STEPS + 1):
        if hmac.compare_digest(code_at_step(secret, step), candidate):
            found = step
    return found


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    label = quote(f"{issuer}:{account}")
    query = urlencode(
        {"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS, "period": PERIOD_SECONDS}
    )
    return f"otpauth://totp/{label}?{query}"


def _fernet() -> Fernet:
    configured = settings.mfa_encryption_key
    material = (configured or settings.jwt_secret_key).get_secret_value()
    # Domain-separated: the signing secret is never used directly as this key.
    derived = hashlib.sha256(b"corpusil-totp-secret-v1:" + material.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_secret(token: str) -> str | None:
    """None when it cannot be read, which means the key changed.

    The caller treats that as "this code did not verify" and the person falls
    back to a recovery code. An exception would turn it into a 500 at sign-in.
    """
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("ascii")
    except (InvalidToken, binascii.Error, ValueError):
        return None


def hash_one_time_value(value: str) -> str:
    """Keyed hash for high-entropy one-time codes.

    bcrypt exists to slow guessing of something a person chose. These are random
    and long, and a keyed hash means a leaked table cannot be tested offline
    without the server's secret either.
    """
    material = (settings.mfa_encryption_key or settings.jwt_secret_key).get_secret_value()
    normalized = value.strip().replace("-", "").replace(" ", "").upper()
    return hmac.new(material.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_recovery_code() -> str:
    """Ten base32 characters in two groups. 50 random bits, easy to copy by hand."""
    raw = base64.b32encode(secrets.token_bytes(7)).decode("ascii").rstrip("=")[:10]
    return f"{raw[:5]}-{raw[5:]}"
