"""
Utility functions for Strava token management
"""
import httpx
from sqlalchemy.orm import Session

from apps.shared.config import settings
from apps.shared.oauth_tokens import (
    HTTP_TIMEOUT,
    TokenSet,
    needs_refresh,
    parse_expiry,
    parse_token_response,
    refresh_token_locked,
)
from apps.strava.models import StravaAuth

# Strava access tokens last 6 hours; refresh an hour ahead of expiry.
REFRESH_BUFFER_SECONDS = 3600


def _exchange_refresh_token(refresh_token: str) -> TokenSet:
    """Trade a refresh token for a new grant at Strava."""
    client_id = settings.strava_client_id
    client_secret = settings.strava_client_secret
    if not client_id or not client_secret:
        raise ValueError("Strava credentials not configured")

    response = httpx.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=HTTP_TIMEOUT,
    )
    if response.status_code != 200:
        # The provider's raw body can carry request details; keep it out of the
        # exception message and let the status code identify the failure.
        raise RuntimeError(f"Strava token refresh failed with HTTP {response.status_code}")

    token_data = parse_token_response(response)
    return TokenSet(
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        expires_at=parse_expiry(token_data),
    )


def refresh_strava_token() -> None:
    """Refresh the stored Strava grant under a row lock, in its own session."""
    refresh_token_locked(StravaAuth, _exchange_refresh_token, REFRESH_BUFFER_SECONDS)


def get_valid_token(db: Session) -> str:
    """Return a currently-valid access token, refreshing first if needed."""
    auth = db.query(StravaAuth).filter(StravaAuth.id == 1).first()
    if not auth:
        raise ValueError("No Strava authentication found. Please complete OAuth flow first.")

    if needs_refresh(auth.expires_at, REFRESH_BUFFER_SECONDS):
        refresh_strava_token()
        # The refresh committed on a separate session, so this one still holds the
        # pre-refresh row; re-read it rather than handing out the dead token.
        db.refresh(auth)

    return auth.access_token
