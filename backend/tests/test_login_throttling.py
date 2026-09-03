"""Login was the only unthrottled endpoint that runs bcrypt.

That made it both a credential-guessing target and the cheapest way to burn
the server's CPU, since every attempt costs a deliberate key-derivation delay
whether or not the password is right.
"""

from __future__ import annotations

import pytest

from tests.helpers import unique_email
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.services.rate_limit import user_rate_limiter


@pytest.fixture(autouse=True)
async def _clean_limiter():
    await user_rate_limiter.clear()
    yield
    await user_rate_limiter.clear()


async def _post_login(client: AsyncClient, email: str, password: str = "wrong-password"):
    return await client.post("/auth/login", json={"email": email, "password": password})


@pytest.mark.integration
async def test_repeated_failures_against_one_account_are_throttled() -> None:
    from main import app

    limit = settings.login_attempts_per_account_per_minute
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # One stable address, so the per-account bucket is what trips.
        victim = unique_email("victim")
        statuses = [
            (await _post_login(client, victim)).status_code
            for _ in range(limit + 2)
        ]

    assert statuses[:limit] == [401] * limit
    assert statuses[limit] == 429


@pytest.mark.integration
async def test_the_throttle_response_carries_retry_after() -> None:
    from main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        target = unique_email("retryafter")
        for _ in range(settings.login_attempts_per_account_per_minute + 1):
            response = await _post_login(client, target)

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1


@pytest.mark.integration
async def test_the_message_does_not_reveal_which_bucket_tripped() -> None:
    """Distinguishing per-account from per-source discloses account existence."""
    from main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        one_account = unique_email("same-account")
        for _ in range(settings.login_attempts_per_account_per_minute + 1):
            account = await _post_login(client, one_account)

        await user_rate_limiter.clear()
        for index in range(settings.login_attempts_per_minute + 1):
            source = await _post_login(client, unique_email(f"spray-{index}"))

    assert account.status_code == 429
    assert source.status_code == 429
    assert account.json()["detail"] == source.json()["detail"]


@pytest.mark.integration
async def test_spraying_many_accounts_from_one_client_is_throttled() -> None:
    """A per-account limit alone is bypassed by rotating the account."""
    from main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        statuses = [
            (await _post_login(client, unique_email(f"spray-target-{index}"))).status_code
            for index in range(settings.login_attempts_per_minute + 2)
        ]

    assert 429 in statuses, "rotating the account must not bypass the source limit"


async def test_limiter_prunes_buckets_it_will_never_read_again() -> None:
    """Login identities are caller-supplied, so the key space is unbounded."""
    for index in range(50):
        await user_rate_limiter.admit(f"user-{index}", "login_account", limit=5)

    assert await user_rate_limiter.prune(window_seconds=0) == 50
    # A bucket still inside its window survives.
    await user_rate_limiter.admit("recent", "login_account", limit=5)
    assert await user_rate_limiter.prune(window_seconds=60) == 0
