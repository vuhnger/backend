"""
Calendar Models
Database models for storing advent calendar data
"""

from sqlalchemy import Column, Integer, String, JSON, DateTime
from sqlalchemy.sql import func
from apps.shared.database import Base


class CalendarDay(Base):
    """
    Represents a single day in the advent calendar

    Each day has:
    - day: Day number (1-24)
    - type: Type of content (text, code, wordle, etc.)
    - data: JSON data specific to the content type
    """
    __tablename__ = "calendar_days"

    id = Column(Integer, primary_key=True, index=True)
    day = Column(Integer, unique=True, nullable=False, index=True)
    type = Column(String(50), nullable=False)
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        """Convert model to dictionary for API response"""
        return {
            "day": self.day,
            "type": self.type,
            **self.data  # Spread the JSON data into the response
        }
