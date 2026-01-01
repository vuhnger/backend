"""
Strava service constants
"""
from datetime import datetime, timezone

# Minimum year for stats - no data before 2024 is synced or queryable
MIN_YEAR = 2024

# Cutoff date for activity sync (start of MIN_YEAR, UTC)
# Using timezone-aware datetime since Strava API works with UTC timestamps
ACTIVITY_CUTOFF = datetime(MIN_YEAR, 1, 1, tzinfo=timezone.utc)
