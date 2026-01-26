"""Sikkerhetsheaders for API-tjenester."""

from fastapi import FastAPI, Request
from fastapi.responses import Response


DEFAULT_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https:; "
    "font-src 'self' data: https:; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "connect-src 'self'"
)


def setup_security_headers(app: FastAPI) -> None:
    """Legg til Content-Security-Policy header."""

    @app.middleware("http")
    async def add_csp_header(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", DEFAULT_CSP)
        return response
