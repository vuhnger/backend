"""Cache-Control header for API-tjenester."""

from fastapi import FastAPI, Request
from fastapi.responses import Response


def setup_cache_control(app: FastAPI) -> None:
    """Legg til Cache-Control header for ikke-cachet innhold."""

    @app.middleware("http")
    async def add_cache_control(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault(
            "Cache-Control",
            "no-cache, no-store, must-revalidate",
        )
        return response
