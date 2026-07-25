"""Oversized bodies are refused before anything reads them.

The upload endpoint's own size check runs after FastAPI has already parsed the
multipart body and spooled its file parts to disk — and after the API-key
dependency, so an unauthenticated request could land 25 MB on the host and still
get a 401. This cap has to bite earlier than all of that.
"""

import pytest
from fastapi import APIRouter
from starlette.testclient import TestClient

from apps.shared.app_factory import create_app, include_versioned
from apps.shared.config import settings

LIMIT = 1024


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "max_request_body_bytes", LIMIT)
    monkeypatch.setattr(settings, "rate_limit_default", "1000/minute")
    app = create_app(title="probe", url_prefix="probe")
    router = APIRouter(prefix="/probe")
    consumed: list[int] = []

    @router.post("/echo")
    async def echo(body: bytes = b""):
        consumed.append(len(body))
        return {"len": len(body)}

    include_versioned(app, router)
    client = TestClient(app)
    client.consumed = consumed  # type: ignore[attr-defined]
    return client


def test_oversized_body_is_rejected_with_413(client):
    resp = client.post("/probe/echo", content=b"x" * (LIMIT + 1))
    assert resp.status_code == 413
    assert resp.json() == {"detail": "Request body too large"}


def test_the_handler_never_sees_an_oversized_body(client):
    # The whole point: rejection happens before the body reaches application code.
    client.post("/probe/echo", content=b"x" * (LIMIT * 100))
    assert client.consumed == []


def test_body_at_the_limit_is_accepted(client):
    assert client.post("/probe/echo", content=b"x" * LIMIT).status_code != 413


def test_requests_without_a_body_are_unaffected(client):
    assert client.get("/probe/openapi.json").status_code == 200
