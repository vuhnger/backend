"""Rate limiting is wired into every app via the shared factory."""

import importlib
import os

from starlette.testclient import TestClient


def test_default_limit_returns_429_when_exceeded():
    os.environ["RATE_LIMIT_DEFAULT"] = "3/minute"
    import apps.shared.rate_limit as rl

    importlib.reload(rl)
    from fastapi import FastAPI

    app = FastAPI()
    rl.setup_rate_limiting(app)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    client = TestClient(app)
    codes = [client.get("/ping").status_code for _ in range(5)]
    assert 429 in codes, codes
    assert codes[:3] == [200, 200, 200]
    os.environ.pop("RATE_LIMIT_DEFAULT", None)


def test_ratelimit_headers_emitted():
    import apps.shared.rate_limit as rl

    importlib.reload(rl)
    from fastapi import FastAPI

    app = FastAPI()
    rl.setup_rate_limiting(app)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    headers = {k.lower() for k in TestClient(app).get("/ping").headers}
    assert "x-ratelimit-limit" in headers
