"""
API Key Authentication Middleware

Simple API key-based authentication for internal services.
Checks for X-API-Key header and validates against environment variable.
"""

import os
from fastapi import Request, HTTPException, status
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware

# API key header name
API_KEY_HEADER = "X-API-Key"

# Get API key from environment
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")

# FastAPI dependency for API key
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


async def get_api_key(api_key: str = api_key_header) -> str:
    """
    Dependency to validate API key from header

    Usage in endpoints:
    @router.get("/protected")
    def protected_endpoint(api_key: str = Depends(get_api_key)):
        # This endpoint requires valid API key
        pass
    """
    if not INTERNAL_API_KEY:
        # API key not configured - allow access (development mode)
        return None

    if api_key is None or api_key != INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )

    return api_key


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce API key on all routes except excluded paths

    Usage:
    app.add_middleware(APIKeyMiddleware, exclude_paths=["/health", "/docs"])
    """

    def __init__(self, app, exclude_paths: list[str] = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or []

    async def dispatch(self, request: Request, call_next):
        # Skip authentication for excluded paths
        if any(request.url.path.endswith(path) for path in self.exclude_paths):
            return await call_next(request)

        # Skip if API key not configured (development mode)
        if not INTERNAL_API_KEY:
            return await call_next(request)

        # Check API key
        api_key = request.headers.get(API_KEY_HEADER)

        if api_key != INTERNAL_API_KEY:
            return HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key"
            )

        return await call_next(request)
