from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_request_id_and_server_timing_are_returned() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": "ui-test-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "ui-test-123"
    assert response.headers["Server-Timing"].startswith("app;dur=")


@pytest.mark.asyncio
async def test_invalid_request_id_is_not_reflected() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": "bad value with spaces"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "bad value with spaces"
    assert len(response.headers["X-Request-ID"]) == 32
