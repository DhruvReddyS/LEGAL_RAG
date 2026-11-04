"""A per-user cap on open job streams.

Each stream polls the database twice a second for as long as it is open. Nothing
stopped one signed-in user opening them until the pool and the host felt it.
Per process, as the existing rate limiter is: the deployment runs one API worker.
"""

from __future__ import annotations

from collections import Counter
from threading import Lock


class StreamLimitReached(Exception):
    pass


class JobStreamGate:
    def __init__(self) -> None:
        self._open: Counter[str] = Counter()
        self._lock = Lock()

    def acquire(self, user_id: str, *, limit: int) -> None:
        with self._lock:
            if self._open[user_id] >= limit:
                raise StreamLimitReached
            self._open[user_id] += 1

    def release(self, user_id: str) -> None:
        with self._lock:
            self._open[user_id] -= 1
            if self._open[user_id] <= 0:
                del self._open[user_id]

    def open_count(self, user_id: str) -> int:
        with self._lock:
            return self._open[user_id]


job_stream_gate = JobStreamGate()
