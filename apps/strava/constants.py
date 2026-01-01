"""
Strava service constants
"""
from datetime import datetime

# Minimum year for stats - no data before 2024 is synced or queryable
MIN_YEAR = 2024

# Cutoff date for activity sync (start of MIN_YEAR)
ACTIVITY_CUTOFF = datetime(MIN_YEAR, 1, 1)
