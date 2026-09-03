from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from time import monotonic


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


user_rate_limiter = UserRateLimiter()
