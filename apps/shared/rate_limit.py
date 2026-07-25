"""Shared rate limiting (slowapi).

A per-IP default limit is applied to every route via SlowAPIMiddleware, so no
per-endpoint decorators are needed for the baseline. Stricter per-route limits
can still be added with `@limiter.limit(...)` where an endpoint takes a
`request: Request` argument.

Storage is in-memory (per process). That's fine for this single-worker,
low-traffic deployment; point `RATE_LIMIT_STORAGE_URI` at Redis if it ever runs
multi-worker and the limit needs to be shared.
"""

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from apps.shared.config import settings
from apps.shared.net import client_ip


def setup_rate_limiting(app: FastAPI) -> Limiter:
    """Attach a per-IP rate limiter with a sensible default to every route.

    Keyed by ``apps.shared.net.client_ip`` — without it every caller behind caddy
    would share one bucket and a single visitor could rate-limit the whole site.
    """
    limiter = Limiter(
        key_func=client_ip,
        default_limits=[settings.rate_limit_default],
        storage_uri=settings.rate_limit_storage_uri,  # None -> in-memory
        headers_enabled=True,  # emit X-RateLimit-* response headers
    )
    app.state.limiter = limiter
    # slowapi's handler signature is narrower than Starlette's generic type.
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)
    return limiter
