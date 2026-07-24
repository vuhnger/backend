"""Regression guards for the security-header + local-Swagger hardening.

Uses the n8n app: it needs no database, so these run with no external services.
"""

from fastapi.testclient import TestClient

from apps.n8n.main import app

client = TestClient(app)


def test_all_security_headers_present():
    r = client.get("/n8n/openapi.json")
    assert r.status_code == 200
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "max-age=31536000" in r.headers["strict-transport-security"]
    assert r.headers["cache-control"] == "no-cache, no-store, must-revalidate"


def test_global_csp_is_strict():
    # Regular API responses must NOT allow inline scripts. The global policy is
    # "…; script-src 'self'; …" — the trailing ';' proves nothing follows 'self'.
    csp = client.get("/n8n/openapi.json").headers["content-security-policy"]
    assert "script-src 'self';" in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]


def test_docs_served_locally_with_scoped_csp():
    r = client.get("/n8n/docs")
    assert r.status_code == 200
    # Swagger assets come from /static, never a third-party CDN.
    assert "/static/swagger-ui/swagger-ui-bundle.js" in r.text
    assert "cdn.jsdelivr.net" not in r.text
    # The inline-script relaxation Swagger needs is scoped to the docs response.
    assert "script-src 'self' 'unsafe-inline'" in r.headers["content-security-policy"]


def test_redoc_disabled():
    # redoc_url=None — no ReDoc route pulling external assets.
    assert client.get("/redoc").status_code == 404
