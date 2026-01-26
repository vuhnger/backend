"""X-Content-Type-Options header for API-tjenester."""

from fastapi import FastAPI, Request
from fastapi.responses import Response


def setup_nosniff_header(app: FastAPI) -> None:
    """Legg til X-Content-Type-Options header."""

    @app.middleware("http")
    async def add_nosniff_header(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response
