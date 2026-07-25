"""Projects list endpoints are bounded, and slug uniqueness is decided by the DB.

Both are DB-free: the pagination bounds are rejected during request validation,
and the slug race is exercised by substituting the session.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from starlette.testclient import TestClient

from apps.projects.main import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, app
from apps.shared.auth import get_api_key
from apps.shared.database import get_db

client = TestClient(app)

LIST_PATHS = ["/projects", "/projects/featured"]


# --- pagination bounds -----------------------------------------------------

@pytest.mark.parametrize("path", LIST_PATHS)
@pytest.mark.parametrize("query", ["limit=0", f"limit={MAX_PAGE_SIZE + 1}", "offset=-1"])
def test_out_of_range_paging_is_rejected(path, query):
    assert client.get(f"{path}?{query}").status_code == 422


@pytest.mark.parametrize("path", LIST_PATHS)
def test_paging_defaults_are_documented(path):
    schema = app.openapi()["paths"][f"/v1{path}"]["get"]
    params = {p["name"]: p["schema"] for p in schema["parameters"]}
    assert params["limit"]["default"] == DEFAULT_PAGE_SIZE
    assert params["limit"]["maximum"] == MAX_PAGE_SIZE


# --- slug race -------------------------------------------------------------

class _ConflictingSession:
    """A session whose commit loses the race to a concurrent insert."""

    def __init__(self):
        self.rolled_back = False

    def add(self, obj):
        pass

    def commit(self):
        raise IntegrityError("INSERT", {}, Exception("duplicate key value"))

    def rollback(self):
        self.rolled_back = True

    def refresh(self, obj):
        raise AssertionError("must not refresh after a failed commit")


@pytest.fixture
def conflicting_db():
    session = _ConflictingSession()
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_api_key] = lambda: "test-key"
    yield session
    app.dependency_overrides.clear()


def test_duplicate_slug_returns_400_not_500(conflicting_db):
    # Previously a check-then-insert: between the SELECT and the INSERT a
    # concurrent create of the same slug slipped through as an unhandled 500.
    resp = client.post(
        "/projects",
        json={"title": "T", "slug": "taken", "description": "d"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Slug already exists"
    assert conflicting_db.rolled_back
