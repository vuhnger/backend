"""
WakaTime database models for OAuth tokens and cached statistics

This module defines two tables:
1. wakatime_auth - Single-row table (id=1) for OAuth tokens
2. wakatime_stats - Multi-row table for cached statistics by type

Follows the proven Strava integration pattern with WakaTime-specific adjustments.
"""
from sqlalchemy import Column, Integer, String, DateTime, JSON, func
from apps.shared.database import Base


class WakaTimeAuth(Base):
    """
    Single-row table for storing OAuth tokens (single user mode).
    Only one row should ever exist with id=1.

    Key differences from Strava:
    - user_id (String) instead of athlete_id (BigInteger) - WakaTime uses UUID strings
    - Longer token columns (500 chars) - WakaTime tokens can be longer
    - token_type column for OAuth compliance
    """
    __tablename__ = "wakatime_auth"

    id = Column(Integer, primary_key=True)  # Always 1 for single user
    user_id = Column(String(255), nullable=False, index=True)  # WakaTime user ID (UUID)
    access_token = Column(String(500), nullable=False)  # Longer than Strava (255)
    refresh_token = Column(String(500), nullable=False)
    expires_at = Column(Integer, nullable=False)  # Unix timestamp
    token_type = Column(String(50), default="Bearer")  # OAuth token type
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WakaTimeStats(Base):
    """
    Cached WakaTime statistics to avoid hitting rate limits.

    Stats types:
    - today: Today's coding time
    - last_7_days: 7-day summary with languages/projects
    - last_30_days: 30-day summary (optional)
    - all_time: All-time totals
    - languages: Language breakdown
    - projects: Project breakdown

    Each stats_type is UNIQUE - upserts will update existing rows.
    """
    __tablename__ = "wakatime_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stats_type = Column(String(50), nullable=False, unique=True, index=True)
    data = Column(JSON, nullable=False)  # PostgreSQL will use JSONB automatically
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "type": self.stats_type,
            "data": self.data,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None
        }
