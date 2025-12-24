"""
Strava database models for OAuth tokens and cached statistics
"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, JSON, func
from apps.shared.database import Base


class StravaAuth(Base):
    """
    Single-row table for storing OAuth tokens (single user mode).
    Only one row should ever exist with id=1.
    """
    __tablename__ = "strava_auth"

    id = Column(Integer, primary_key=True)  # Always 1 for single user
    athlete_id = Column(BigInteger, nullable=False, index=True)
    access_token = Column(String(255), nullable=False)
    refresh_token = Column(String(255), nullable=False)
    expires_at = Column(Integer, nullable=False)  # Unix timestamp
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class StravaStats(Base):
    """
    Cached Strava statistics to avoid hitting rate limits.
    Different stats_type values: ytd, recent_activities, monthly
    """
    __tablename__ = "strava_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stats_type = Column(String(50), nullable=False, unique=True, index=True)
    data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "type": self.stats_type,
            "data": self.data,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None
        }
