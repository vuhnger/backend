"""
API Key Authentication

Simple API key-based authentication for internal services: add
``Depends(get_api_key)`` to any endpoint that must require one.

An ``APIKeyMiddleware`` used to live here too. It had no callers, and two bugs
that would have bitten the first one: it matched exclusions with ``endswith``, so
``/projects/evil/health`` bypassed authentication entirely, and it raised
``HTTPException`` from inside ``BaseHTTPMiddleware``, which Starlette turns into a
500 rather than a 401. Removed rather than fixed — the dependency above already
covers every real use.
"""

import hmac
import logging

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from apps.shared.config import settings

# Setup logging
logger = logging.getLogger(__name__)

# API key header name
API_KEY_HEADER = "X-API-Key"

# Get API key and environment from environment variables
INTERNAL_API_KEY = settings.internal_api_key
ENVIRONMENT = settings.environment

# FastAPI dependency for API key
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


async def get_api_key(api_key: str = Security(api_key_header)) -> str | None:
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
