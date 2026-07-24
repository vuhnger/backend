"""DB-backed regression: the strava app boots against Postgres, its health
endpoint reports a live connection, and security headers apply to a DB-backed
service too.

Skips when no database is reachable so the header tests above can still run
locally without spinning up Postgres. CI provides a Postgres service, so these
execute there.
"""

import pytest
from fastapi.testclient import TestClient

from apps.shared.database import check_db_connection


@pytest.fixture(scope="module")
def strava_client():
    if not check_db_connection():
        pytest.skip("no database reachable (set DATABASE_URL to a live Postgres)")
    # Imported lazily: apps.strava.main runs create_all() at import, which needs
    # a live connection — only reached once we know the DB is up.
    from apps.strava.main import app

    return TestClient(app)


def test_strava_health_reports_connected(strava_client):
    r = strava_client.get("/strava/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


def test_security_headers_on_db_backed_app(strava_client):
    r = strava_client.get("/strava/openapi.json")
    assert r.headers["x-frame-options"] == "DENY"
    assert "script-src 'self';" in r.headers["content-security-policy"]
