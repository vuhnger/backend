"""Anti-clickjacking headers for API-tjenester."""

from fastapi import FastAPI, Request
from fastapi.responses import Response


def setup_clickjacking_headers(app: FastAPI) -> None:
    """Legg til X-Frame-Options header."""

    @app.middleware("http")
    async def add_x_frame_options(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response
