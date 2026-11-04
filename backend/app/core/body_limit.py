"""Refuse an oversized request before the application reads it.

FastAPI reads the body before it solves dependencies, so authentication runs
after the bytes have landed: an unauthenticated client could post a very large
JSON body to /auth/login and have all of it held in memory, or spool a huge
multipart upload to temporary disk ahead of the 401. uvicorn sets no limit.

Pure ASGI, so a declared Content-Length is refused without touching the body and
a chunked stream is counted as it arrives.
"""

from __future__ import annotations

import json
import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

MIB = 1024 * 1024
# Everything that is not an upload is a small JSON document.
DEFAULT_BODY_LIMIT = 2 * MIB
# Any other multipart route. A route added later should get a useful answer
# rather than an unexplained refusal.
DEFAULT_MULTIPART_LIMIT = 32 * MIB

# The application bound plus one MiB for the multipart envelope, so the route's
# own check still gives the precise message for a file just over its limit.
_UPLOAD_LIMITS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"^/cases/[^/]+/storage/objects$"), 26 * MIB),
    (re.compile(r"^/admin/corpus/intakes$"), 31 * MIB),
    (re.compile(r"^/citizen/documents/extract$"), 11 * MIB),
)


class _BodyTooLarge(Exception):
    pass


def body_limit_for(path: str, content_type: str) -> int:
    for pattern, limit in _UPLOAD_LIMITS:
        if pattern.match(path):
            return limit
    if content_type.lower().startswith("multipart/form-data"):
        return DEFAULT_MULTIPART_LIMIT
    return DEFAULT_BODY_LIMIT


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    async def _refuse(send: Send) -> None:
        body = json.dumps({"detail": "Request body is too large"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        limit = body_limit_for(
            scope.get("path", ""),
            headers.get(b"content-type", b"").decode("latin-1"),
        )
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                too_large = int(declared) > limit
            except ValueError:
                too_large = False
            if too_large:
                await self._refuse(send)
                return

        received = 0
        exceeded = False
        response_started = False

        async def counting_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _BodyTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            # FastAPI turns a failure while reading the body into a 400. Once the
            # limit has tripped, that answer is wrong: drop it and send the 413.
            if exceeded and not response_started:
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except _BodyTooLarge:
            pass
        if exceeded and not response_started:
            await self._refuse(send)
