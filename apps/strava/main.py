"""
Strava Service API

OAuth integration for Strava with cached statistics.
Single user mode - stores one set of tokens and serves cached data.
"""
import os
import logging
from fastapi import FastAPI, APIRouter, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from stravalib.client import Client

from apps.shared.database import get_db, Base, engine, check_db_connection
from apps.shared.auth import get_api_key
from apps.shared.oauth_state import generate_state, validate_state
from apps.shared.errors import log_and_sanitize_error
from apps.strava.models import StravaAuth, StravaStats
from apps.strava.tasks import fetch_and_cache_stats

logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Strava Service",
    version="1.0.0",
    description="Strava OAuth integration with cached activity statistics"
)

# CORS Configuration
origins = [
    "https://vuhnger.dev",
    "https://vuhnger.github.io",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router setup
router = APIRouter(prefix="/strava")


@router.get("/health")
def health():
    """Health check endpoint"""
    db_connected = check_db_connection()
    return {
        "status": "ok" if db_connected else "degraded",
        "service": "strava",
        "database": "connected" if db_connected else "disconnected"
    }


@router.get("/authorize")
def authorize():
    """
    Initiate OAuth flow by redirecting to Strava.
    User will be redirected to Strava to authorize the app.
    """
    client_id = os.getenv("STRAVA_CLIENT_ID")
    redirect_uri = os.getenv("STRAVA_REDIRECT_URI")

    if not client_id or not redirect_uri:
        raise HTTPException(status_code=500, detail="Strava OAuth not configured")

    # Generate secure per-request state for CSRF protection
    state = generate_state()

    # Build authorization URL
    authorize_url = f"https://www.strava.com/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope=read,activity:read_all&state={state}"

    return RedirectResponse(url=authorize_url)


@router.get("/callback")
def oauth_callback(code: str, state: str, db: Session = Depends(get_db)):
    """
    OAuth callback endpoint.
    Strava redirects here after user authorizes.
    Exchanges code for tokens and stores in database.
    """
    # Verify state for CSRF protection
    if not validate_state(state):
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter")
    
    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Strava OAuth not configured")

    try:
        # Exchange code for tokens
        client = Client()
        token_response = client.exchange_code_for_token(
            client_id=client_id,
            client_secret=client_secret,
            code=code
        )

        # Extract token data
        access_token = token_response["access_token"]
        refresh_token = token_response["refresh_token"]
        expires_at = token_response["expires_at"]

        # Get athlete ID - either from token response or by fetching athlete
        if "athlete" in token_response and "id" in token_response["athlete"]:
            athlete_id = token_response["athlete"]["id"]
        else:
            # Fetch athlete info using the access token
            client.access_token = access_token
            athlete = client.get_athlete()
            athlete_id = athlete.id

        # Store in database (single user, id=1) using atomic upsert
        from apps.shared.upsert import atomic_upsert_auth

        atomic_upsert_auth(
            db=db,
            model=StravaAuth,
            auth_data={
                'id': 1,
                'athlete_id': athlete_id,
                'access_token': access_token,
                'refresh_token': refresh_token,
                'expires_at': expires_at
            }
        )
        db.commit()
    except Exception as e:
        # Rollback any pending database changes to maintain session consistency
        db.rollback()
        sanitized_msg, error_id = log_and_sanitize_error(
            e,
            "OAuth token exchange",
            "OAuth authorization failed. Please try again."
        )
        raise HTTPException(status_code=500, detail=sanitized_msg)
    
    # Trigger initial data fetch (async would be better, but simple sync for now)
    try:
        fetch_and_cache_stats()
    except Exception as e:
        logger.warning(f"Initial data fetch failed: {e}", exc_info=True)

    # Redirect to frontend success page
    frontend_url = os.getenv("FRONTEND_URL", "https://vuhnger.dev")
    return RedirectResponse(url=f"{frontend_url}/?strava=success")


@router.get("/stats/ytd")
def get_ytd_stats(db: Session = Depends(get_db)):
    """
    Get cached year-to-date statistics.
    Returns run and ride totals for current year.
    """
    stats = db.query(StravaStats).filter(StravaStats.stats_type == "ytd").first()
    
    if not stats:
        raise HTTPException(
            status_code=404,
            detail="YTD stats not cached yet. Try /strava/refresh-data"
        )
    
    return stats.to_dict()


@router.get("/stats/activities")
def get_activities(db: Session = Depends(get_db)):
    """
    Get cached recent activities (last 30).
    Returns list of activities with basic info.
    """
    stats = db.query(StravaStats).filter(StravaStats.stats_type == "recent_activities").first()
    
    if not stats:
        raise HTTPException(
            status_code=404,
            detail="Activities not cached yet. Try /strava/refresh-data"
        )
    
    return stats.to_dict()


@router.get("/stats/monthly")
def get_monthly_stats(db: Session = Depends(get_db)):
    """
    Get cached monthly aggregated statistics.
    Returns monthly summaries for last 12 months.
    """
    stats = db.query(StravaStats).filter(StravaStats.stats_type == "monthly").first()
    
    if not stats:
        raise HTTPException(
            status_code=404,
            detail="Monthly stats not cached yet. Try /strava/refresh-data"
        )
    
    return stats.to_dict()


@router.post("/refresh-data")
def refresh_data(api_key: str = Depends(get_api_key)):
    """
    Manually trigger data refresh from Strava.
    Protected endpoint - requires X-API-Key header.
    """
    try:
        fetch_and_cache_stats()
        return {"status": "success", "message": "Data refreshed successfully"}
    except Exception as e:
        sanitized_msg, error_id = log_and_sanitize_error(
            e,
            "Data refresh",
            "Failed to refresh Strava data"
        )
        raise HTTPException(status_code=500, detail=sanitized_msg)


app.include_router(router)
