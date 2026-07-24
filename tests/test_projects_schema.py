"""Regression tests for the Projects pydantic schemas.

These lock in pydantic v2 behaviour. The projects endpoints call
`project_data.model_dump()` — a v2-only method. When stravalib 1.6 capped the
tree to pydantic 1, `model_dump()` didn't exist and create/update 500'd. If a
future change ever pins pydantic back to v1, these tests fail loudly instead of
the bug reaching production.
"""

import pydantic

from apps.projects.schemas import ProjectCreate, ProjectResponse, ProjectUpdate


def test_pydantic_is_v2():
    assert pydantic.VERSION.startswith("2."), pydantic.VERSION


def test_project_create_model_dump():
    pc = ProjectCreate(title="Demo", slug="demo-project")
    data = pc.model_dump()
    assert data["slug"] == "demo-project"
    assert data["published"] is False  # default carried through


def test_project_update_excludes_unset():
    # Only the field we set should appear — this is exactly what the PUT handler
    # relies on to patch selectively.
    update = ProjectUpdate(title="New title")
    assert update.model_dump(exclude_unset=True) == {"title": "New title"}


def test_project_response_from_orm_attributes():
    # from_attributes=True must let a response be built straight off an ORM row.
    class Row:
        pass

    row = Row()
    row.__dict__.update(
        ProjectCreate(title="Demo", slug="demo").model_dump(),
        id=7,
        created_at=None,
        updated_at=None,
    )
    resp = ProjectResponse.model_validate(row)
    assert resp.id == 7 and resp.slug == "demo"
