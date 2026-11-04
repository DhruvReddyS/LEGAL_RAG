"""A request too large to serve is refused before the application reads it."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.core.body_limit import (
    DEFAULT_BODY_LIMIT,
    DEFAULT_MULTIPART_LIMIT,
    MIB,
    BodySizeLimitMiddleware,
    body_limit_for,
)


def _app() -> tuple[FastAPI, list[int]]:
    seen: list[int] = []
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware)

    @app.post("/echo")
    async def echo(request: Request) -> dict:
        body = await request.body()
        seen.append(len(body))
        return {"bytes": len(body)}

    @app.post("/parsed")
    async def parsed(payload: dict) -> dict:
        seen.append(1)
        return payload

    return app, seen


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_a_small_body_reaches_the_handler() -> None:
    app, seen = _app()
    async with _client(app) as client:
        response = await client.post("/echo", content=b"x" * 1024)
    assert response.status_code == 200
    assert seen == [1024]


@pytest.mark.asyncio
async def test_a_declared_oversize_is_refused_without_running_the_handler() -> None:
    app, seen = _app()
    async with _client(app) as client:
        response = await client.post("/echo", content=b"x" * (DEFAULT_BODY_LIMIT + 1))
    assert response.status_code == 413
    assert seen == []


@pytest.mark.asyncio
async def test_a_chunked_body_with_no_content_length_is_counted() -> None:
    """The declared length is the attacker's to omit."""
    app, seen = _app()

    async def stream():
        for _ in range(4):
            yield b"x" * (DEFAULT_BODY_LIMIT // 2)

    async with _client(app) as client:
        response = await client.post("/echo", content=stream())
    assert response.status_code == 413
    assert seen == []


@pytest.mark.asyncio
async def test_a_chunked_oversize_is_a_413_on_a_route_that_parses_json() -> None:
    """FastAPI turns a failure reading the body into a 400 of its own."""
    app, seen = _app()

    async def stream():
        for _ in range(4):
            yield b"x" * (DEFAULT_BODY_LIMIT // 2)

    async with _client(app) as client:
        response = await client.post(
            "/parsed", content=stream(), headers={"Content-Type": "application/json"}
        )
    assert response.status_code == 413
    assert seen == []


def test_uploads_get_their_own_allowance_and_json_does_not() -> None:
    assert body_limit_for("/auth/login", "application/json") == DEFAULT_BODY_LIMIT
    assert body_limit_for("/cases/abc/storage/objects", "multipart/form-data; boundary=x") == 26 * MIB
    assert body_limit_for("/admin/corpus/intakes", "multipart/form-data; boundary=x") == 31 * MIB
    assert body_limit_for("/citizen/documents/extract", "multipart/form-data; boundary=x") == 11 * MIB
    assert body_limit_for("/anything", "multipart/form-data; boundary=x") == DEFAULT_MULTIPART_LIMIT
