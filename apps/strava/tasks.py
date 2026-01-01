"""
Background tasks for fetching and caching Strava data
"""
import logging
import time
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from apps.shared.database import SessionLocal
from apps.strava.models import StravaStats, StravaActivity
from apps.strava.client import get_recent_activities, get_monthly_stats, get_all_activities
from apps.strava.constants import ACTIVITY_CUTOFF
from apps.shared.upsert import atomic_upsert_stats

logger = logging.getLogger(__name__)

# Rate limiting: Strava allows 100 requests per 15 minutes
# Add delay between batches to stay well under limit
RATE_LIMIT_DELAY_SECONDS = 1.0


def fetch_and_cache_stats():
    """
    Fetch all stats from Strava and cache in database.
    This function should be called by a cron job or scheduler.

    All stats are committed atomically - either all succeed or all fail.
    """
    db = SessionLocal()

    try:
        logger.info("Fetching Strava data...")

        # Sync activities from 2024 onwards
        sync_activities(db)
        logger.info("Synced activities to database")

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


def sync_activities(db: Session):
    """
    Fetch activities from 2024 onwards and upsert them into the database.
    Uses efficient bulk upsert with rate limiting to respect Strava API limits.
    """
    activities_gen = get_all_activities(db, after=ACTIVITY_CUTOFF)

    count = 0
    batch = []
    batch_count = 0
    BATCH_SIZE = 100

    for activity_data in activities_gen:
        batch.append(activity_data)
        count += 1

        if len(batch) >= BATCH_SIZE:
            _bulk_upsert_activities(db, batch)
            db.flush()  # Persist to DB but keep transaction open
            batch = []
            batch_count += 1
            logger.info(f"Synced {count} activities...")

            # Rate limiting: pause between batches to respect Strava API limits
            time.sleep(RATE_LIMIT_DELAY_SECONDS)

    if batch:
        _bulk_upsert_activities(db, batch)
        db.flush()

    logger.info(f"Total activities synced: {count} in {batch_count + 1} batches")


def _bulk_upsert_activities(db: Session, activities: List[Dict[str, Any]]):
    """
    Helper to perform bulk upsert of activities
    """
    if not activities:
        return

    stmt = pg_insert(StravaActivity.__table__).values(activities)
    
    # Update all fields on conflict except id
    update_dict = {
        c.name: c for c in stmt.excluded 
        if c.name != 'id'
    }
    
    stmt = stmt.on_conflict_do_update(
        index_elements=['id'],
        set_=update_dict
    )
    
    db.execute(stmt)


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
