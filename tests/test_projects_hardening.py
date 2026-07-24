"""Hardening regression tests for the Projects app.

Covers the audit fixes: security headers (#3), the /admin route-ordering fix
(#2), CORS dev-origin gating (#4), and upload content validation (#5). All are
DB-free — the projects app imports without a live database.
"""

import os

from starlette.testclient import TestClient

from apps.projects.main import app

client = TestClient(app)


def test_security_headers_present():  # #3
    h = client.get("/projects/health").headers
    assert "content-security-policy" in h
    assert h.get("x-frame-options") == "DENY"
    assert h.get("x-content-type-options") == "nosniff"


def test_docs_served_locally_not_cdn():  # #3
    body = client.get("/projects/docs").text
    assert "/static/swagger-ui" in body
    assert "cdn.jsdelivr" not in body


def test_admin_route_not_shadowed_by_slug():  # #2
    # /admin must reach the admin panel, not be captured as /{slug} (which would
    # 404 with "Project not found").
    r = client.get("/projects/admin")
    assert r.status_code == 200
    assert "Project not found" not in r.text


def test_cors_gates_dev_origins_by_environment(monkeypatch):  # #4
    import apps.shared.cors as cors
    from apps.shared.config import settings

    # get_allowed_origins() reads settings.is_production at call time, so patch
    # the singleton (env+reload wouldn't reach the cached Settings).
    monkeypatch.setattr(settings, "environment", "production")
    assert not any("localhost" in o for o in cors.get_allowed_origins())

    monkeypatch.setattr(settings, "environment", "development")
    assert any("localhost" in o for o in cors.get_allowed_origins())


def test_upload_rejects_non_image_content():  # #5
    # Bytes that aren't an image, even with an image content-type header, are
    # rejected by the magic-byte check (filetype) before anything is written.
    r = client.post(
        "/projects/upload-image",
        files={"file": ("evil.png", b"this is not an image", "image/png")},
        headers={"X-API-Key": os.environ["INTERNAL_API_KEY"]},
    )
    assert r.status_code == 400
    assert "valid" in r.json()["detail"].lower()
