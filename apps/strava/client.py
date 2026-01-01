"""
Strava API client wrapper using stravalib
"""
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Any, Optional, Generator
from stravalib.client import Client
from sqlalchemy.orm import Session
from apps.strava.utils import get_valid_token


def get_recent_activities(db: Session, limit: int = 30) -> List[Dict[str, Any]]:
    """
    Fetch recent activities from Strava.
    Returns: list of activity dictionaries
    """
    access_token = get_valid_token(db)
    client = Client(access_token=access_token)

    # Get recent activities
    activities = client.get_activities(limit=limit)

    result = []
    for activity in activities:
        result.append({
            "id": activity.id,
            "name": activity.name,
            "type": activity.type,
            "distance": float(activity.distance) if activity.distance else 0,  # meters
            "moving_time": int(activity.moving_time.total_seconds()) if activity.moving_time else 0,  # seconds
            "elevation_gain": float(activity.total_elevation_gain) if activity.total_elevation_gain else 0,
            "start_date": activity.start_date.isoformat() if activity.start_date else None
        })

    return result


def get_monthly_stats(db: Session, months: int = 12) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate activities by month for the last N months.
    Returns: dict with monthly summaries
    """
    access_token = get_valid_token(db)
    client = Client(access_token=access_token)

    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months * 30)

    # Get activities in date range
    activities = client.get_activities(after=start_date, before=end_date)

    # Aggregate by month
    monthly_data = defaultdict(lambda: {
        "count": 0,
        "distance": 0,
        "moving_time": 0,
        "elevation_gain": 0
    })

    for activity in activities:
        if activity.start_date:
            month_key = activity.start_date.strftime("%Y-%m")
            monthly_data[month_key]["count"] += 1
            monthly_data[month_key]["distance"] += (
                float(activity.distance) if activity.distance else 0
            )
            monthly_data[month_key]["moving_time"] += (
                int(activity.moving_time.total_seconds()) if activity.moving_time else 0
            )
            monthly_data[month_key]["elevation_gain"] += (
                float(activity.total_elevation_gain) if activity.total_elevation_gain else 0
            )

    # Convert to sorted list
    result = {}
    for month, data in sorted(monthly_data.items(), reverse=True):
        result[month] = data

    return result


def get_all_activities(db: Session, after: Optional[datetime] = None, limit: Optional[int] = None) -> Generator[Dict[str, Any], None, None]:
    """
    Fetch activities from Strava, optionally after a given date.
    Yields activity data dictionaries suitable for StravaActivity model.

    Args:
        db: Database session for token access
        after: Only fetch activities after this datetime (server-side filter)
        limit: Maximum number of activities to fetch (None for all)
    """
    access_token = get_valid_token(db)
    client = Client(access_token=access_token)

    # Get activities (paginated automatically by stravalib)
    activities = client.get_activities(after=after, limit=limit)

    for activity in activities:
        yield {
            "id": activity.id,
            "name": activity.name,
            "type": activity.type,
            "distance": float(activity.distance) if activity.distance else 0.0,
            "moving_time": int(activity.moving_time.total_seconds()) if activity.moving_time else 0,
            "elapsed_time": int(activity.elapsed_time.total_seconds()) if activity.elapsed_time else 0,
            "total_elevation_gain": float(activity.total_elevation_gain) if activity.total_elevation_gain else 0.0,
            "start_date": activity.start_date,
            "start_date_local": activity.start_date_local,
            "timezone": str(activity.timezone),
            "average_speed": float(activity.average_speed) if activity.average_speed else 0.0,
            "max_speed": float(activity.max_speed) if activity.max_speed else 0.0,
            "average_heartrate": float(activity.average_heartrate) if hasattr(activity, 'average_heartrate') and activity.average_heartrate else None,
            "max_heartrate": float(activity.max_heartrate) if hasattr(activity, 'max_heartrate') and activity.max_heartrate else None,
            "kudos_count": int(activity.kudos_count) if hasattr(activity, 'kudos_count') else 0
        }
