"""Shared FastAPI application factory.

Every service app repeated the same ~25-line block: build the FastAPI instance
with the built-in docs disabled, wire the three shared middlewares (CORS,
cache-control, security headers), mount the local ``/static`` assets, and
register a locally-served Swagger UI under ``/<prefix>/docs``.

Centralizing it here means a new service is a single ``create_app()`` call and
the security hardening can never silently drift between apps.
"""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import get_swagger_ui_oauth2_redirect_html
from fastapi.staticfiles import StaticFiles
from starlette.types import Lifespan

from apps.shared.body_limit import BodySizeLimitMiddleware
from apps.shared.cache_control_headers import setup_cache_control
from apps.shared.config import settings
from apps.shared.cors import setup_cors
from apps.shared.logging_config import configure_logging
from apps.shared.rate_limit import setup_rate_limiting
from apps.shared.security_headers import setup_security_headers
from apps.shared.swagger_ui import render_swagger_ui_html


def create_app(
    *,
    title: str,
    url_prefix: str,
    description: str = "",
    version: str = "1.0.0",
    lifespan: Lifespan | None = None,
) -> FastAPI:
    """Build a hardened FastAPI app with locally-served docs under ``/<url_prefix>/docs``.

    Args:
        title: Human-readable service title (shown in the docs).
        url_prefix: Path segment the service lives under (e.g. ``"strava"``);
            drives ``openapi.json`` and the docs routes.
        description: Optional OpenAPI description.
        version: OpenAPI version string.
        lifespan: Optional async context manager for startup/shutdown work.
            Every app so far is stateless and needs none; the site service holds
            open WebSockets and has to close them deliberately on SIGTERM, or
            clients see a dropped connection instead of a close frame and answer
            it with a reconnect storm.

    Returns:
        A configured ``FastAPI`` instance. Callers add their own routers.
    """
    configure_logging()
    prefix = url_prefix.strip("/")

    app = FastAPI(
        title=title,
        version=version,
        description=description,
        lifespan=lifespan,
        # Built-in docs are disabled so Swagger UI is served from local /static
        # assets under a strict CSP instead of a third-party CDN.
        docs_url=None,
        redoc_url=None,
        openapi_url=f"/{prefix}/openapi.json",
    )

    # Shared middleware, applied in one place so hardening can't drift per-app.
    # The body cap is added last so it ends up outermost: an oversized request
    # must be refused before any other layer — or FastAPI itself — reads it.
    setup_cors(app)
    setup_cache_control(app)
    setup_security_headers(app)
    setup_rate_limiting(app)
    app.add_middleware(
        BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes
    )

    # Compress responses here rather than relying on the reverse proxy: Caddy
    # doesn't compress unless explicitly told to, and that config lives outside
    # this repo. The route-geometry endpoint is ~1.3 MB uncompressed and ~230 KB
    # gzipped, which is the difference between comfortably meeting the frontend's
    # 5 s budget on mobile and not. The threshold keeps small JSON responses
    # untouched, where compression would cost more than it saves.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # Serve Swagger UI assets locally (no third-party CDN) so the strict CSP applies.
    app.mount("/static", StaticFiles(directory="static"), name="static")

    docs_url = f"/{prefix}/docs"
    oauth2_redirect_url = f"{docs_url}/oauth2-redirect"

    @app.get(docs_url, include_in_schema=False)
    def swagger_ui_html():
        return render_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=app.title,
            oauth2_redirect_url=oauth2_redirect_url,
        )

    @app.get(oauth2_redirect_url, include_in_schema=False)
    def swagger_ui_redirect():
        return get_swagger_ui_oauth2_redirect_html()

    return app


def include_versioned(app: FastAPI, router: APIRouter, *, latest: str = "/v1") -> None:
    """Mount a router at the versioned path and keep the bare path as an alias.

    Backward-compatible API versioning: the router is served at ``/<latest>/…``
    (the documented, canonical path) and also at its bare path — the latter
    hidden from the schema so it reads as a deprecated alias. Existing clients
    (the frontend, Strava's configured OAuth redirect) keep working unchanged
    while new consumers can move to ``/v1``.
    """
    app.include_router(router, prefix=latest)
    app.include_router(router, include_in_schema=False)
