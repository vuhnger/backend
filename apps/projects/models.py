"""
Projects database models.

Stores project information including metadata, images, and links.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB

from apps.shared.database import Base


class Project(Base):
    """
    Project model for portfolio projects.

    Stores all project data including:
    - Basic info (title, description, content)
    - Media (image URL)
    - Metadata (technologies, links)
    - Display settings (featured, order, published)
    """
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    slug = Column(String(100), unique=True, index=True, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    content = Column(Text)  # Markdown for detailed description
    image_url = Column(String(500))
    technologies = Column(JSONB, default=list)  # ["React", "Python", "PostgreSQL"]
    links = Column(JSONB, default=dict)  # {"github": "...", "live": "...", "demo": "..."}
    featured = Column(Boolean, default=False)
    order = Column(Integer, default=0)
    published = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    def to_dict(self) -> dict:
        """Convert project to dictionary for API responses."""
        return {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "description": self.description,
            "content": self.content,
            "image_url": self.image_url,
            "technologies": self.technologies or [],
            "links": self.links or {},
            "featured": self.featured,
            "order": self.order,
            "published": self.published,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
