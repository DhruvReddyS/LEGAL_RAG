from __future__ import annotations

import pytest

from app.services.rate_limit import RateLimitExceeded, UserRateLimiter


@pytest.mark.asyncio
async def test_rate_limit_isolated_by_user_and_bucket() -> None:
    limiter = UserRateLimiter()
    await limiter.admit("user-a", "jobs", limit=2)
    await limiter.admit("user-a", "jobs", limit=2)

    with pytest.raises(RateLimitExceeded) as captured:
        await limiter.admit("user-a", "jobs", limit=2)

    assert captured.value.retry_after_seconds >= 1
    await limiter.admit("user-b", "jobs", limit=2)
    await limiter.admit("user-a", "fast", limit=2)


@pytest.mark.asyncio
async def test_rate_limit_clear_restores_admission() -> None:
    limiter = UserRateLimiter()
    await limiter.admit("user-a", "jobs", limit=1)
    with pytest.raises(RateLimitExceeded):
        await limiter.admit("user-a", "jobs", limit=1)
    await limiter.clear()
    await limiter.admit("user-a", "jobs", limit=1)
