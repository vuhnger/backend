"""
Pydantic schemas for Projects API.

Defines request/response models with validation.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ProjectBase(BaseModel):
    """Base schema with common project fields."""
    title: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    content: Optional[str] = None
    image_url: Optional[str] = None
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
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    slug: Optional[str] = Field(None, min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    content: Optional[str] = None
    image_url: Optional[str] = None
    technologies: Optional[list[str]] = None
    links: Optional[dict[str, str]] = None
    featured: Optional[bool] = None
    order: Optional[int] = None
    published: Optional[bool] = None


class ProjectResponse(ProjectBase):
    """Schema for project responses."""
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ImageUploadResponse(BaseModel):
    """Response after successful image upload."""
    url: str
    filename: str
