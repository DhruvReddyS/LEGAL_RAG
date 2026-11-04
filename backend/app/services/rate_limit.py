from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from time import monotonic

from fastapi import HTTPException, status

from app.core.config import settings


@dataclass(frozen=True)
class RateLimitExceeded(Exception):
    retry_after_seconds: int


class UserRateLimiter:
    """Small per-process sliding-window limiter for the four-user pilot.

    The API currently runs as one backend process. A shared Redis limiter is
    required before adding multiple API replicas; this class intentionally
    makes no cross-process guarantee.
    """

    def __init__(self) -> None:
        self._requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def admit(
        self,
        user_id: str,
        bucket: str,
        *,
        limit: int,
        window_seconds: int = 60,
    ) -> None:
        now = monotonic()
        cutoff = now - window_seconds
        key = (user_id, bucket)
        async with self._lock:
            timestamps = self._requests[key]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= limit:
                retry_after = max(1, int(window_seconds - (now - timestamps[0]) + 0.999))
                raise RateLimitExceeded(retry_after)
            timestamps.append(now)

    async def clear(self) -> None:
        async with self._lock:
            self._requests.clear()

    async def prune(self, *, window_seconds: int = 60) -> int:
        """Drop buckets with no recent activity.

        The dictionary is keyed on (identity, bucket) and grew without bound;
        for the login buckets the identity is caller-supplied, so an unbounded
        key space is reachable from outside.
        """
        cutoff = monotonic() - window_seconds
        async with self._lock:
            stale = [
                key
                for key, timestamps in self._requests.items()
                if not timestamps or timestamps[-1] <= cutoff
            ]
            for key in stale:
                del self._requests[key]
            return len(stale)


user_rate_limiter = UserRateLimiter()


async def enforce_rate_limit(identity: str, bucket: str, *, limit: int, detail: str) -> None:
    """Admit a request or answer 429, for routes with nothing else to do on refusal."""
    try:
        await user_rate_limiter.admit(identity, bucket, limit=limit)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


async def enforce_llm_sync_limit(user_id: object) -> None:
    await enforce_rate_limit(
        str(user_id),
        "llm_sync",
        limit=settings.llm_sync_requests_per_minute,
        detail="Too many analysis requests. Try again shortly.",
    )
