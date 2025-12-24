"""
Strava API client wrapper using stravalib
"""
from datetime import datetime, timedelta
from collections import defaultdict
from stravalib.client import Client
from sqlalchemy.orm import Session
from apps.strava.utils import get_valid_token


def get_ytd_stats(db: Session) -> dict:
    """
    Fetch year-to-date statistics from Strava.
    Returns: dict with counts, distances, times, elevation
    """
    access_token = get_valid_token(db)
    client = Client(access_token=access_token)
    
    # Get athlete stats
    athlete = client.get_athlete()
    stats = client.get_athlete_stats(athlete.id)
    
    # Extract YTD totals
    ytd_run = stats.ytd_run_totals
    ytd_ride = stats.ytd_ride_totals
    
    return {
        "run": {
            "count": ytd_run.count,
            "distance": float(ytd_run.distance),  # meters
            "moving_time": ytd_run.moving_time,  # seconds
            "elevation_gain": float(ytd_run.elevation_gain)  # meters
        },
        "ride": {
            "count": ytd_ride.count,
            "distance": float(ytd_ride.distance),
            "moving_time": ytd_ride.moving_time,
            "elevation_gain": float(ytd_ride.elevation_gain)
        }
    }


def get_recent_activities(db: Session, limit: int = 30) -> list:
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
            "moving_time": activity.moving_time.seconds if activity.moving_time else 0,
            "elevation_gain": float(activity.total_elevation_gain) if activity.total_elevation_gain else 0,
            "start_date": activity.start_date.isoformat() if activity.start_date else None
        })
    
    return result


def get_monthly_stats(db: Session, months: int = 12) -> dict:
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
            monthly_data[month_key]["distance"] += float(activity.distance) if activity.distance else 0
            monthly_data[month_key]["moving_time"] += activity.moving_time.seconds if activity.moving_time else 0
            monthly_data[month_key]["elevation_gain"] += float(activity.total_elevation_gain) if activity.total_elevation_gain else 0
    
    # Convert to sorted list
    result = {}
    for month, data in sorted(monthly_data.items(), reverse=True):
        result[month] = data
    
    return result
