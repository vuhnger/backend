"""
Background tasks for fetching and caching Strava data
"""
import logging
from typing import Dict, Any
from sqlalchemy.orm import Session
from apps.shared.database import SessionLocal
from apps.strava.models import StravaStats
from apps.strava.client import get_ytd_stats, get_recent_activities, get_monthly_stats
from apps.shared.upsert import atomic_upsert_stats

logger = logging.getLogger(__name__)


def fetch_and_cache_stats():
    """
    Fetch all stats from Strava and cache in database.
    This function should be called by a cron job or scheduler.

    All stats are committed atomically - either all succeed or all fail.
    """
    db = SessionLocal()

    try:
        logger.info("Fetching Strava data...")

        # Fetch YTD stats
        ytd_data = get_ytd_stats(db)
        upsert_stats(db, "ytd", ytd_data, commit=False)
        logger.info("YTD stats prepared")

        # Fetch recent activities
        activities_data = get_recent_activities(db, limit=30)
        upsert_stats(db, "recent_activities", activities_data, commit=False)
        logger.info(f"Prepared {len(activities_data)} recent activities")

        # Fetch monthly stats
        monthly_data = get_monthly_stats(db, months=12)
        upsert_stats(db, "monthly", monthly_data, commit=False)
        logger.info(f"Prepared monthly stats for {len(monthly_data)} months")

        # Commit all changes atomically
        db.commit()
        logger.info("All Strava data cached successfully")

    except Exception as e:
        # Rollback all pending changes on any failure
        db.rollback()
        logger.error(f"Error fetching Strava data: {e}", exc_info=True)
        raise
    finally:
        db.close()


def upsert_stats(db: Session, stats_type: str, data: Dict[str, Any], commit: bool = True) -> None:
    """
    Atomic insert or update of cached stats using PostgreSQL ON CONFLICT.

    This replaces the old unsafe check-then-insert pattern which had race conditions:

    OLD UNSAFE PATTERN (race condition):
        existing = db.query(StravaStats).filter(...).first()  # SELECT
        if existing:
            existing.data = data  # UPDATE
        else:
            db.add(StravaStats(...))  # INSERT
        db.commit()

    Problem: Between the SELECT and INSERT, another process could insert the same
    stats_type, causing a duplicate key violation.

    NEW ATOMIC PATTERN (race-free):
        Uses PostgreSQL's INSERT ON CONFLICT DO UPDATE in a single atomic operation.
        No race condition possible - the database handles conflicts atomically.

    Performance improvements:
        - Eliminates SELECT query (2 queries -> 1 query)
        - Prevents duplicate key violations under concurrent load
        - ~2-3x throughput improvement (see benchmark_upsert.py)

    Args:
        db: Database session
        stats_type: Type of stats (ytd, recent_activities, monthly)
        data: Stats data to store
        commit: Whether to commit immediately (default True for backward compatibility).
                Set to False for atomic multi-operation transactions.
    """
    atomic_upsert_stats(
        db=db,
        model=StravaStats,
        unique_field='stats_type',
        unique_value=stats_type,
        update_data={'data': data}
    )

    if commit:
        db.commit()


if __name__ == "__main__":
    # Allow running directly for testing
    fetch_and_cache_stats()
