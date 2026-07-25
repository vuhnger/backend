"""
Projects API

CRUD endpoints for portfolio projects with image upload support.
"""
import logging
import os
from uuid import uuid4

import aiofiles
import filetype
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.projects.models import Project
from apps.projects.schemas import (
    ImageUploadResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from apps.shared.app_factory import create_app, include_versioned
from apps.shared.auth import get_api_key
from apps.shared.config import settings
from apps.shared.database import check_db_connection, get_db

logger = logging.getLogger(__name__)

# Schema is managed by Alembic migrations (`alembic upgrade head`), not created
# at import time. See alembic/ and `make migrate`.

# Upload configuration
UPLOAD_DIR = settings.upload_dir
UPLOAD_BASE_URL = settings.upload_base_url
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# The list endpoints used to end in a bare .all(). The table is small today, but
# an unbounded query is a latent outage: it grows into one silently, and the
# strava app already caps its own listing at 200 for exactly this reason.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

# Hardened app: CORS, cache-control, security headers, and locally-served docs
# (matches the other services; a strict CSP would block CDN-hosted Swagger).
app = create_app(
    title="Projects API",
    url_prefix="projects",
    description="Portfolio projects management with image uploads",
)

router = APIRouter(prefix="/projects", tags=["projects"])


# ──────────────────────────────────────────────────────────────────────────────
# Public endpoints (no auth required)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/health")
def health():
    """Health check endpoint."""
    db_connected = check_db_connection()
    return {
        "status": "ok" if db_connected else "degraded",
        "service": "projects",
        "database": "connected" if db_connected else "disconnected",
    }


@router.get("", response_model=list[ProjectResponse])
def list_published_projects(
    db: Session = Depends(get_db),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
):
    """
    List published projects, newest-ordered.
    Sorted by order (ascending), then by created_at (descending).
    """
    projects = (
        db.query(Project)
        .filter(Project.published == True)
        .order_by(Project.order.asc(), Project.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return projects


@router.get("/featured", response_model=list[ProjectResponse])
def list_featured_projects(
    db: Session = Depends(get_db),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
):
    """List featured projects (for homepage display)."""
    projects = (
        db.query(Project)
        .filter(Project.published == True, Project.featured == True)
        .order_by(Project.order.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return projects


@router.get("/admin", include_in_schema=False)
def admin_panel():
    """Serve the admin panel HTML.

    Registered before the /{slug} route below — otherwise FastAPI matches the
    dynamic route first and 'admin' is swallowed as a project slug (404).
    """
    admin_path = os.path.join(os.path.dirname(__file__), "..", "..", "static", "admin.html")
    if not os.path.exists(admin_path):
        raise HTTPException(status_code=404, detail="Admin panel not found")
    return FileResponse(admin_path)


@router.get("/{slug}", response_model=ProjectResponse)
def get_project(slug: str, db: Session = Depends(get_db)):
    """Get a single published project by slug."""
    project = (
        db.query(Project)
        .filter(Project.slug == slug, Project.published == True)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# ──────────────────────────────────────────────────────────────────────────────
# Admin endpoints (API key required)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/admin/all", response_model=list[ProjectResponse])
def list_all_projects(
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
):
    """List projects including unpublished (admin only)."""
    projects = (
        db.query(Project)
        .order_by(Project.order.asc(), Project.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return projects


@router.get("/admin/{slug}", response_model=ProjectResponse)
def get_project_admin(
    slug: str,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """Get any project by slug (admin only, includes unpublished)."""
    project = db.query(Project).filter(Project.slug == slug).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(
    project_data: ProjectCreate,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """Create a new project."""
    project = Project(**project_data.model_dump())
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        # Let the database's unique constraint be the arbiter instead of a
        # preceding SELECT: between the check and the insert, a concurrent create
        # of the same slug slipped through and surfaced as an unhandled 500.
        db.rollback()
        raise HTTPException(status_code=400, detail="Slug already exists") from None
    db.refresh(project)
    return project


@router.put("/{slug}", response_model=ProjectResponse)
def update_project(
    slug: str,
    project_data: ProjectUpdate,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """Update an existing project."""
    project = db.query(Project).filter(Project.slug == slug).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Update only provided fields
    update_data = project_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)

    try:
        db.commit()
    except IntegrityError:
        # Same race as create: the unique constraint decides, not a prior SELECT.
        db.rollback()
        raise HTTPException(status_code=400, detail="Slug already exists") from None
    db.refresh(project)
    return project


@router.delete("/{slug}", status_code=204)
def delete_project(
    slug: str,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """Delete a project."""
    project = db.query(Project).filter(Project.slug == slug).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(project)
    db.commit()


@router.post("/upload-image", response_model=ImageUploadResponse)
async def upload_image(
    file: UploadFile = File(...),
    api_key: str = Depends(get_api_key),
):
    """
    Upload an image for a project.
    Returns the public URL of the uploaded image.
    """
    too_large = f"File too large. Max size: {MAX_FILE_SIZE // (1024 * 1024)} MB"

    # Reject oversized uploads before buffering the whole body into memory.
    # UploadFile.size comes from the multipart part length when the client sends it.
    if file.size is not None and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=too_large)

    # The declared content-type is client-controlled; treat it as a first filter
    # only, then confirm against the real bytes below.
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(sorted(ALLOWED_TYPES))}",
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:  # size wasn't advertised — enforce after read
        raise HTTPException(status_code=400, detail=too_large)

    # Validate the real bytes, not the client's content-type header, with the
    # `filetype` library. Also take the extension from the detected type so a
    # hostile filename can't drive what we write to disk.
    kind = filetype.guess(contents)
    if kind is None or kind.mime not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="File content is not a valid JPEG, PNG, WebP or GIF image",
        )

    filename = f"{uuid4().hex}.{kind.extension}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    # Ensure upload directory exists
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Save file
    async with aiofiles.open(filepath, "wb") as f:
        await f.write(contents)

    logger.info(f"Uploaded image: {filename}")

    return ImageUploadResponse(
        url=f"{UPLOAD_BASE_URL}/{filename}",
        filename=filename,
    )


include_versioned(app, router)
