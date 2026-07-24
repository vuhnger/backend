"""Rate limiting is wired into every app via the shared factory."""

from fastapi import FastAPI
from starlette.testclient import TestClient

from apps.shared.config import settings
from apps.shared.rate_limit import setup_rate_limiting


def _app_with_ping() -> FastAPI:
    app = FastAPI()
    setup_rate_limiting(app)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return app


def test_default_limit_returns_429_when_exceeded(monkeypatch):
    # setup_rate_limiting reads settings.rate_limit_default at call time; patch
    # the singleton (the cached Settings won't pick up an env change).
    monkeypatch.setattr(settings, "rate_limit_default", "3/minute")
    client = TestClient(_app_with_ping())
    codes = [client.get("/ping").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert 429 in codes, codes


def test_ratelimit_headers_emitted():
    headers = {k.lower() for k in TestClient(_app_with_ping()).get("/ping").headers}
    assert "x-ratelimit-limit" in headers
