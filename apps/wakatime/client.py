"""
WakaTime API client wrapper
"""
import logging
from datetime import datetime, date
import requests
from sqlalchemy.orm import Session
from apps.wakatime.utils import get_valid_token

logger = logging.getLogger(__name__)

BASE_URL = "https://wakatime.com/api/v1"

def get_stats(db: Session, time_range: str = "last_7_days"):
    """
    Fetch stats for a specific time range.
    Ranges: last_7_days, last_30_days, last_6_months, last_year, all_time
    """
    access_token = get_valid_token(db)
    
    url = f"{BASE_URL}/users/current/stats/{time_range}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json().get("data", {})
    except requests.RequestException as e:
        logger.error(f"Failed to fetch WakaTime stats ({time_range}): {e}")
        raise

def get_today_summary(db: Session):
    """
    Fetch summary for today.
    """
    access_token = get_valid_token(db)
    
    today_str = date.today().strftime("%Y-%m-%d")
    url = f"{BASE_URL}/users/current/summaries"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "start": today_str,
        "end": today_str
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json().get("data", [])
        return data[0] if data else {}
    except requests.RequestException as e:
        logger.error(f"Failed to fetch WakaTime today summary: {e}")
        raise

def get_all_time_stats(db: Session):
    """
    Fetch all time stats.
    """
    return get_stats(db, "all_time")
