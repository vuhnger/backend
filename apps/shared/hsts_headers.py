"""HSTS header for API-tjenester."""

from fastapi import FastAPI, Request
from fastapi.responses import Response


def setup_hsts_header(app: FastAPI) -> None:
    """Legg til Strict-Transport-Security header."""

    @app.middleware("http")
    async def add_hsts_header(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains; preload",
        )
        return response
