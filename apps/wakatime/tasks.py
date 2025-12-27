"""
Background tasks for fetching and caching WakaTime data
"""
import logging
from sqlalchemy.orm import Session
from apps.shared.database import SessionLocal
from apps.wakatime.models import WakaTimeStats, WakaTimeAuth
from apps.wakatime.client import get_stats, get_today_summary, get_weekly_summary
from apps.shared.upsert import atomic_upsert_stats

logger = logging.getLogger(__name__)

def fetch_and_cache_wakatime_stats():
    """
    Fetch all stats from WakaTime and cache in database.
    """
    db = SessionLocal()

    try:
        logger.info("Fetching WakaTime data...")
        
        # Check if authenticated
        auth = db.query(WakaTimeAuth).first()
        if not auth:
            logger.warning("No WakaTime authentication found.")
            return

        # 1. Fetch Today's Summary
        today_data = get_today_summary(db)
        atomic_upsert_stats(
            db=db,
            model=WakaTimeStats,
            unique_field='stats_type',
            unique_value='today',
            update_data={'data': today_data}
        )
        logger.info("Cached 'today' stats")

        # 2. Fetch Last 7 Days (using accurate summaries)
        last_7_days = get_weekly_summary(db)
        atomic_upsert_stats(
            db=db,
            model=WakaTimeStats,
            unique_field='stats_type',
            unique_value='last_7_days',
            update_data={'data': last_7_days}
        )
        logger.info("Cached 'last_7_days' summary (accurate)")

        # 3. Fetch All Time
        all_time = get_stats(db, "all_time")
        atomic_upsert_stats(
            db=db,
            model=WakaTimeStats,
            unique_field='stats_type',
            unique_value='all_time',
            update_data={'data': all_time}
        )
        logger.info("Cached 'all_time' stats")

        db.commit()
        logger.info("All WakaTime data cached successfully")

    except Exception as e:
        db.rollback()
        logger.error(f"Error fetching WakaTime data: {e}", exc_info=True)
        raise
    finally:
        db.close()

if __name__ == "__main__":
    fetch_and_cache_wakatime_stats()
