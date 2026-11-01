"""Backward-compatible API versioning: /v1 is canonical, bare path is a hidden alias."""

from starlette.testclient import TestClient

from apps.site.main import app  # DB-free app is enough to exercise the routing

client = TestClient(app)


def test_v1_and_legacy_paths_both_work():
    assert client.get("/site/health").status_code == 200          # legacy alias
    assert client.get("/v1/site/health").status_code == 200       # canonical


def test_openapi_documents_only_v1():
    paths = client.get("/site/openapi.json").json()["paths"]
    assert any(p.startswith("/v1/site") for p in paths)
    # The bare service paths must be hidden from the schema (deprecated alias).
    assert not any(p.startswith("/site/") and p != "/site/openapi.json" for p in paths)
