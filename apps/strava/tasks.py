"""
Background tasks for fetching and caching Strava data
"""
from sqlalchemy.orm import Session
from apps.shared.database import SessionLocal
from apps.strava.models import StravaStats
from apps.strava.client import get_ytd_stats, get_recent_activities, get_monthly_stats


def fetch_and_cache_stats():
    """
    Fetch all stats from Strava and cache in database.
    This function should be called by a cron job or scheduler.
    """
    db = SessionLocal()
    
    try:
        print("Fetching Strava data...")
        
        # Fetch YTD stats
        ytd_data = get_ytd_stats(db)
        upsert_stats(db, "ytd", ytd_data)
        print("YTD stats cached")
        
        # Fetch recent activities
        activities_data = get_recent_activities(db, limit=30)
        upsert_stats(db, "recent_activities", activities_data)
        print(f"Cached {len(activities_data)} recent activities")
        
        # Fetch monthly stats
        monthly_data = get_monthly_stats(db, months=12)
        upsert_stats(db, "monthly", monthly_data)
        print(f"Cached monthly stats for {len(monthly_data)} months")
        
        print("All Strava data cached successfully")
        
    except Exception as e:
        print(f"Error fetching Strava data: {e}")
        raise
    finally:
        db.close()


def upsert_stats(db: Session, stats_type: str, data: dict):
    """
    Insert or update cached stats in database
    """
    # Check if stats already exist
    existing = db.query(StravaStats).filter(StravaStats.stats_type == stats_type).first()
    
    if existing:
        # Update existing
        existing.data = data
        db.commit()
    else:
        # Insert new
        stats = StravaStats(stats_type=stats_type, data=data)
        db.add(stats)
        db.commit()


if __name__ == "__main__":
    # Allow running directly for testing
    fetch_and_cache_stats()
