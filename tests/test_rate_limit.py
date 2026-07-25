"""Rate limiting is enforced on the routes production actually serves.

The previous version of this test registered its probe with ``@app.get()``
directly on a bare FastAPI instance. That is not how any real endpoint is
mounted — every app builds its routes through ``create_app()`` +
``include_versioned()`` — and the difference mattered: the old slowapi-based
limiter resolved limits via the matched route's ``.endpoint`` attribute, which
router-included routes don't have, so production was unlimited while this test
stayed green. Every probe below therefore goes through the real factory.
"""

import pytest
from fastapi import APIRouter, FastAPI
from starlette.testclient import TestClient

from apps.shared.app_factory import create_app, include_versioned
from apps.shared.config import settings


@pytest.fixture
def app(monkeypatch) -> FastAPI:
    # setup_rate_limiting reads the setting at call time; patch the singleton
    # (the cached Settings won't pick up an env change).
    monkeypatch.setattr(settings, "rate_limit_default", "3/minute")
    app = create_app(title="probe", url_prefix="probe")
    router = APIRouter(prefix="/probe")

    @router.get("/ping")
    def ping():
        return {"ok": True}

    @router.get("/health")
    def health():
        return {"status": "ok"}

    include_versioned(app, router)
    return app


def _codes(client: TestClient, path: str, n: int) -> list[int]:
    return [client.get(path).status_code for _ in range(n)]


def test_router_included_route_is_limited(app):
    # The regression that mattered: this path was completely exempt.
    assert _codes(TestClient(app), "/probe/ping", 5) == [200, 200, 200, 429, 429]


def test_versioned_alias_shares_the_same_bucket(app):
    client = TestClient(app)
    _codes(client, "/probe/ping", 3)
    # /v1/... and the bare alias are the same endpoint; hitting one must not
    # hand the caller a fresh allowance on the other.
    assert client.get("/v1/probe/ping").status_code == 429


def test_separate_clients_get_separate_buckets(app):
    client = TestClient(app)
    _codes(client, "/probe/ping", 5)
    other = {"x-forwarded-for": "203.0.113.50"}
    assert client.get("/probe/ping", headers=other).status_code == 200


def test_healthcheck_paths_are_never_throttled(app):
    client = TestClient(app)
    _codes(client, "/probe/ping", 5)  # exhaust the caller's allowance
    # Container healthchecks poll these; throttling them would make autoheal
    # restart a healthy container.
    assert client.get("/probe/health").status_code == 200
    assert client.get("/probe/openapi.json").status_code == 200


def test_limit_headers_are_emitted(app):
    resp = TestClient(app).get("/probe/ping")
    assert resp.headers["X-RateLimit-Limit"] == "3"
    assert resp.headers["X-RateLimit-Remaining"] == "2"


def test_429_tells_the_caller_when_to_retry(app):
    client = TestClient(app)
    _codes(client, "/probe/ping", 4)
    resp = client.get("/probe/ping")
    assert resp.status_code == 429
    assert 0 < int(resp.headers["Retry-After"]) <= 60
