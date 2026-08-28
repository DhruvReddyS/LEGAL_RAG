from __future__ import annotations

from collections.abc import Collection

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_AUTH_COOKIE_NAMES = frozenset({"legal_rag_access", "legal_rag_refresh"})


class DesktopOriginSecurityMiddleware(BaseHTTPMiddleware):
    """Protect credentialed cross-origin desktop requests.

    CORS controls which callers may read responses, but it does not by itself
    prevent a browser from submitting a state-changing cookie request. Require
    an explicitly trusted Origin for every cookie-authenticated mutation and
    for all cookie-login/refresh/logout operations.
    """

    def __init__(
        self,
        app,
        *,
        allowed_origins: Collection[str],
        allow_private_network: bool = False,
    ) -> None:
        super().__init__(app)
        self.allowed_origins = frozenset(allowed_origins)
        self.allow_private_network = allow_private_network

    async def dispatch(self, request: Request, call_next) -> Response:
        origin = request.headers.get("origin")
        unsafe = request.method.upper() not in _SAFE_METHODS
        uses_cookie_auth = bool(_AUTH_COOKIE_NAMES.intersection(request.cookies))
        cookie_auth_endpoint = request.url.path.startswith("/auth/cookie/")

        if unsafe and (uses_cookie_auth or cookie_auth_endpoint):
            if origin not in self.allowed_origins:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Untrusted request origin"},
                )

        response = await call_next(request)
        if (
            self.allow_private_network
            and request.method.upper() == "OPTIONS"
            and origin in self.allowed_origins
            and request.headers.get("access-control-request-private-network", "").lower()
            == "true"
        ):
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response
