"""
API Key Authentication Middleware

Simple API key-based authentication for internal services.
Checks for X-API-Key header and validates against environment variable.
"""

import os
import hmac
import logging
from fastapi import Request, HTTPException, status, Security
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware

# Setup logging
logger = logging.getLogger(__name__)

# API key header name
API_KEY_HEADER = "X-API-Key"

# Get API key and environment from environment variables
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# FastAPI dependency for API key
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


async def get_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Dependency to validate API key from header

    Usage in endpoints:
    @router.get("/protected")
    def protected_endpoint(api_key: str = Depends(get_api_key)):
        # This endpoint requires valid API key
        pass
    """
    if not INTERNAL_API_KEY:
        if ENVIRONMENT == "production":
            raise RuntimeError(
                "INTERNAL_API_KEY must be set in production. "
                "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )
        # Development mode - log warning and allow access
        logger.warning(
            "API key authentication disabled - running in development mode. "
            "Set INTERNAL_API_KEY environment variable for security."
        )
        return None

    # Use constant-time comparison to prevent timing attacks
    if api_key is None or not hmac.compare_digest(api_key, INTERNAL_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Invalid or missing API key",
                "category": "security",
            },
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

        # Check if API key is configured
        if not INTERNAL_API_KEY:
            if ENVIRONMENT == "production":
                raise RuntimeError(
                    "INTERNAL_API_KEY must be set in production. "
                    "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
                )
            # Development mode - log warning and allow access
            logger.warning(
                "API key authentication disabled - running in development mode. "
                "Set INTERNAL_API_KEY environment variable for security."
            )
            return await call_next(request)

        # Check API key using constant-time comparison to prevent timing attacks
        api_key = request.headers.get(API_KEY_HEADER)

        if not api_key or not hmac.compare_digest(api_key, INTERNAL_API_KEY):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "message": "Invalid or missing API key",
                    "category": "security",
                },
            )

        return await call_next(request)
