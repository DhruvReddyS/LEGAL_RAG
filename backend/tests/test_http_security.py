from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.http_security import DesktopOriginSecurityMiddleware


def private_network_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        DesktopOriginSecurityMiddleware,
        allowed_origins=["http://tauri.localhost"],
        allow_private_network=True,
    )

    @app.options("/health")
    async def health_options() -> dict[str, str]:
        return {"status": "ok"}

    return app


@pytest.mark.asyncio
async def test_private_network_header_is_returned_only_to_an_allowed_origin() -> None:
    app = private_network_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        allowed = await client.options(
            "/health",
            headers={
                "Origin": "http://tauri.localhost",
                "Access-Control-Request-Private-Network": "true",
            },
        )
        denied = await client.options(
            "/health",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Private-Network": "true",
            },
        )

    assert allowed.headers["Access-Control-Allow-Private-Network"] == "true"
    assert "Access-Control-Allow-Private-Network" not in denied.headers
