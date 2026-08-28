from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_request_id_and_server_timing_are_returned() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": "ui-test-123"})

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "api_compatibility": "1"}
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Request-ID"] == "ui-test-123"
    assert response.headers["Server-Timing"].startswith("app;dur=")


@pytest.mark.asyncio
async def test_invalid_request_id_is_not_reflected() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": "bad value with spaces"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "bad value with spaces"
    assert len(response.headers["X-Request-ID"]) == 32


@pytest.mark.asyncio
async def test_health_cors_preflight_accepts_only_a_configured_origin() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        allowed = await client.options(
            "/health",
            headers={
                "Origin": "http://tauri.localhost",
                "Access-Control-Request-Method": "GET",
            },
        )
        denied = await client.options(
            "/health",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["Access-Control-Allow-Origin"] == "http://tauri.localhost"
    assert denied.status_code == 400
    assert "Access-Control-Allow-Origin" not in denied.headers


@pytest.mark.asyncio
async def test_untrusted_host_is_rejected_before_health_response() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health", headers={"Host": "attacker.example"})

    assert response.status_code == 400
