"""
Utility functions for Strava token management
"""
import os
import time
from typing import Dict, Any
import requests
from sqlalchemy.orm import Session
from apps.strava.models import StravaAuth


def is_token_expired(expires_at: int) -> bool:
    """Check if token has expired"""
    return time.time() >= expires_at


def needs_refresh(expires_at: int, buffer_seconds: int = 3600) -> bool:
    """Check if token expires within buffer time (default 1 hour)"""
    return time.time() >= (expires_at - buffer_seconds)


def refresh_strava_token(db: Session) -> Dict[str, Any]:
    """
    Refresh Strava access token using refresh token.
    Returns new token data or raises exception.

    Rolls back database changes if token refresh or update fails.
    """
    # Get current auth (single user, id=1)
    auth = db.query(StravaAuth).filter(StravaAuth.id == 1).first()

    if not auth:
        raise ValueError("No Strava authentication found. Please complete OAuth flow first.")

    # Prepare token refresh request
    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError("Strava credentials not configured")

    try:
        # Request new tokens from Strava
        response = requests.post(
            "https://www.strava.com/oauth/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": auth.refresh_token
            }
        )

        if response.status_code != 200:
            raise Exception(f"Failed to refresh token: {response.text}")

        token_data = response.json()

        # Update database with new tokens
        auth.access_token = token_data["access_token"]
        auth.refresh_token = token_data["refresh_token"]
        auth.expires_at = token_data["expires_at"]
        db.commit()

        return token_data

    except Exception:
        # Rollback on any failure (network, API, or database)
        db.rollback()
        raise


def get_valid_token(db: Session) -> str:
    """
    Get a valid access token, refreshing if necessary.
    Returns access token string.
    """
    auth = db.query(StravaAuth).filter(StravaAuth.id == 1).first()

    if not auth:
        raise ValueError("No Strava authentication found. Please complete OAuth flow first.")

    # Check if token needs refresh
    if needs_refresh(auth.expires_at):
        refresh_strava_token(db)
        # Reload auth after refresh
        auth = db.query(StravaAuth).filter(StravaAuth.id == 1).first()

    return auth.access_token
