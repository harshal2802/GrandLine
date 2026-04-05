from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Routes that do NOT require authentication.
# Everything else under /api/ is blocked by default.
PUBLIC_PATHS: set[str] = {
    "/api/v1/health",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
}

# Path prefixes that are always public (static assets, etc.)
PUBLIC_PREFIXES: tuple[str, ...] = (
    "/api/docs",
    "/api/redoc",
)


class DefaultDenyMiddleware(BaseHTTPMiddleware):
    """Block all /api/* requests that lack a valid Authorization header,
    unless the path is explicitly allowlisted.

    Actual token validation is handled by the `get_current_user` dependency
    at the route level. This middleware is a coarse first gate that rejects
    obviously unauthenticated requests early.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path

        # Only gate /api/* routes
        if not path.startswith("/api/"):
            response: Response = await call_next(request)
            return response

        # Allow OPTIONS for CORS preflight
        if request.method == "OPTIONS":
            response = await call_next(request)
            return response

        # Check allowlist
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            response = await call_next(request)
            return response

        # Require Authorization header
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": {
                        "code": "NOT_AUTHENTICATED",
                        "message": "Missing authentication token",
                    }
                },
            )

        response = await call_next(request)
        return response
