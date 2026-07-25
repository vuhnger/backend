"""Shared per-IP rate limiting.

A single default limit is applied to every request, keyed on the real client IP
(``apps.shared.net.client_ip``) so callers behind the proxy don't share a bucket.

This is deliberately built straight on ``limits`` rather than on slowapi. slowapi
enforces limits by looking up the matched route's ``.endpoint`` attribute, and
FastAPI wraps ``include_router()`` routes in an object that has no ``.endpoint``
— so every router-mounted path (i.e. every real endpoint in this repo) was
silently exempt while only the three factory-registered routes were limited. A
limiter that keys off the request alone cannot regress that way.

Storage is in-memory per process, which is right for this single-worker
deployment; point ``RATE_LIMIT_STORAGE_URI`` at Redis to share it across workers.
"""

import math
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from limits import parse
from limits.storage import storage_from_string
from limits.strategies import MovingWindowRateLimiter

from apps.shared.config import settings
from apps.shared.net import client_ip

# Paths exempt from limiting: the container healthchecks poll these every 15-30s
# and must never be throttled into a false 'unhealthy' verdict (which autoheal
# would answer by restarting a perfectly good container).
EXEMPT_SUFFIXES = ("/health", "/openapi.json")


def _is_exempt(path: str) -> bool:
    return path.endswith(EXEMPT_SUFFIXES)


def setup_rate_limiting(app: FastAPI) -> None:
    """Apply a per-IP default limit to every request the app serves."""
    item = parse(settings.rate_limit_default)
    limiter = MovingWindowRateLimiter(
        storage_from_string(settings.rate_limit_storage_uri or "memory://")
    )

    @app.middleware("http")
    async def enforce_rate_limit(request: Request, call_next) -> Response:
        if _is_exempt(request.url.path):
            return await call_next(request)

        key = client_ip(request)
        if not limiter.hit(item, key):
            reset_at, _ = limiter.get_window_stats(item, key)
            retry_after = max(1, math.ceil(reset_at - time.time()))
            return JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(item.amount),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(reset_at)),
                },
            )

        response = await call_next(request)
        reset_at, remaining = limiter.get_window_stats(item, key)
        response.headers["X-RateLimit-Limit"] = str(item.amount)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(reset_at))
        return response
