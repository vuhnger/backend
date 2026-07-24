"""
Pydantic schemas for Projects API.

Defines request/response models with validation.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    """Base schema with common project fields."""
    title: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    content: str | None = None
    image_url: str | None = None
    technologies: list[str] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)
    featured: bool = False
    order: int = 0
    published: bool = False


class ProjectCreate(ProjectBase):
    """Schema for creating a new project."""
    pass


class ProjectUpdate(BaseModel):
    """Schema for updating a project. All fields optional."""
    title: str | None = Field(None, min_length=1, max_length=200)
    slug: str | None = Field(None, min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    content: str | None = None
    image_url: str | None = None
    technologies: list[str] | None = None
    links: dict[str, str] | None = None
    featured: bool | None = None
    order: int | None = None
    published: bool | None = None


class ProjectResponse(ProjectBase):
    """Schema for project responses."""
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ImageUploadResponse(BaseModel):
    """Response after successful image upload."""
    url: str
    filename: str
