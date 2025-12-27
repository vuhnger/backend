"""
Projects API

CRUD endpoints for portfolio projects with image upload support.
"""
import os
import logging
import aiofiles
from uuid import uuid4
from fastapi import FastAPI, APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from apps.shared.database import get_db, Base, engine, check_db_connection
from apps.shared.auth import get_api_key
from apps.shared.cors import setup_cors
from apps.projects.models import Project
from apps.projects.schemas import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ImageUploadResponse,
)

logger = logging.getLogger(__name__)

# Create tables
Base.metadata.create_all(bind=engine)

# Upload configuration
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/home/rocky/uploads/projects")
UPLOAD_BASE_URL = os.getenv("UPLOAD_BASE_URL", "https://api.vuhnger.dev/uploads/projects")
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

app = FastAPI(
    title="Projects API",
    version="1.0.0",
    description="Portfolio projects management with image uploads",
    docs_url="/projects/docs",
    openapi_url="/projects/openapi.json",
)

# Setup CORS from shared configuration
setup_cors(app)

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
def list_published_projects(db: Session = Depends(get_db)):
    """
    List all published projects.
    Sorted by order (ascending), then by created_at (descending).
    """
    projects = (
        db.query(Project)
        .filter(Project.published == True)
        .order_by(Project.order.asc(), Project.created_at.desc())
        .all()
    )
    return projects


@router.get("/featured", response_model=list[ProjectResponse])
def list_featured_projects(db: Session = Depends(get_db)):
    """List all featured projects (for homepage display)."""
    projects = (
        db.query(Project)
        .filter(Project.published == True, Project.featured == True)
        .order_by(Project.order.asc())
        .all()
    )
    return projects


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
):
    """List all projects including unpublished (admin only)."""
    projects = (
        db.query(Project)
        .order_by(Project.order.asc(), Project.created_at.desc())
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
    # Check for duplicate slug
    existing = db.query(Project).filter(Project.slug == project_data.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail="Slug already exists")

    project = Project(**project_data.model_dump())
    db.add(project)
    db.commit()
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

    # Check for slug conflict if changing slug
    if project_data.slug and project_data.slug != slug:
        existing = db.query(Project).filter(Project.slug == project_data.slug).first()
        if existing:
            raise HTTPException(status_code=400, detail="Slug already exists")

    # Update only provided fields
    update_data = project_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)

    db.commit()
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
    # Validate file type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_TYPES)}",
        )

    # Read file and check size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {MAX_FILE_SIZE // (1024*1024)} MB",
        )

    # Generate unique filename
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    filename = f"{uuid4().hex}.{ext}"
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


# ──────────────────────────────────────────────────────────────────────────────
# Admin panel (static HTML)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/admin", include_in_schema=False)
def admin_panel():
    """Serve the admin panel HTML."""
    admin_path = os.path.join(os.path.dirname(__file__), "..", "..", "static", "admin.html")
    if not os.path.exists(admin_path):
        raise HTTPException(status_code=404, detail="Admin panel not found")
    return FileResponse(admin_path)


app.include_router(router)
