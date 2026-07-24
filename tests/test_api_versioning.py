"""Backward-compatible API versioning: /v1 is canonical, bare path is a hidden alias."""

from starlette.testclient import TestClient

from apps.n8n.main import app  # DB-free app is enough to exercise the routing

client = TestClient(app)


def test_v1_and_legacy_paths_both_work():
    assert client.get("/n8n/health").status_code == 200          # legacy alias
    assert client.get("/v1/n8n/health").status_code == 200       # canonical


def test_openapi_documents_only_v1():
    paths = client.get("/n8n/openapi.json").json()["paths"]
    assert any(p.startswith("/v1/n8n") for p in paths)
    # The bare service paths must be hidden from the schema (deprecated alias).
    assert not any(p.startswith("/n8n/") and p != "/n8n/openapi.json" for p in paths)
