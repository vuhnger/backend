"""
Strava Service API

OAuth integration for Strava with cached statistics.
Single user mode - stores one set of tokens and serves cached data.
"""
import os
import logging
from datetime import datetime
from fastapi import FastAPI, APIRouter, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, extract
from stravalib.client import Client

from apps.shared.database import get_db, Base, engine, check_db_connection
from apps.shared.auth import get_api_key
from apps.shared.oauth_state import generate_state, validate_state
from apps.shared.errors import log_and_sanitize_error
from apps.strava.models import StravaAuth, StravaStats, StravaActivity
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
    "http://localhost:3000"
    "https://localhost:3000",
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
    authorize_url = (
        f"https://www.strava.com/oauth/authorize?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope=read,activity:read_all&"
        f"state={state}"
    )

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
        from apps.shared.encryption import encrypt_token

        # Encrypt tokens before storing (use database column names)
        atomic_upsert_auth(
            db=db,
            model=StravaAuth,
            auth_data={
                'id': 1,
                'athlete_id': athlete_id,
                'access_token': encrypt_token(access_token),
                'refresh_token': encrypt_token(refresh_token),
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


@router.get("/stats/longest-run")
def get_longest_run(year: int = None, db: Session = Depends(get_db)):
    """
    Get the longest run for a specific year (default: current year).
    Query from full activity history.
    """
    if year is None:
        year = datetime.now().year

    longest_run = (
        db.query(StravaActivity)
        .filter(
            StravaActivity.type == "Run",
            extract('year', StravaActivity.start_date_local) == year
        )
        .order_by(desc(StravaActivity.distance))
        .first()
    )

    if not longest_run:
        raise HTTPException(
            status_code=404,
            detail=f"No runs found for year {year}. Try /strava/refresh-data"
        )

    return longest_run.to_dict()


@router.get("/stats/longest-ride")
def get_longest_ride(year: int = None, db: Session = Depends(get_db)):
    """
    Get the longest ride for a specific year (default: current year).
    Query from full activity history.
    """
    if year is None:
        year = datetime.now().year

    longest_ride = (
        db.query(StravaActivity)
        .filter(
            StravaActivity.type == "Ride",
            extract('year', StravaActivity.start_date_local) == year
        )
        .order_by(desc(StravaActivity.distance))
        .first()
    )

    if not longest_ride:
        raise HTTPException(
            status_code=404,
            detail=f"No rides found for year {year}. Try /strava/refresh-data"
        )

    return longest_ride.to_dict()


@router.get("/activities")
def get_all_activities_endpoint(
    limit: int = 100,
    offset: int = 0,
    year: int = None,
    activity_type: str = None,
    db: Session = Depends(get_db)
):
    """
    Get all activities from history with pagination and filtering.
    """
    query = db.query(StravaActivity).order_by(desc(StravaActivity.start_date))

    if year:
        query = query.filter(extract('year', StravaActivity.start_date_local) == year)
    
    if activity_type:
        query = query.filter(StravaActivity.type == activity_type)

    total = query.count()
    activities = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [a.to_dict() for a in activities]
    }


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


@app.get("/", response_class=HTMLResponse)
def landing_page():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Strava API Service</title>
        <style>
            body { font-family: system-ui, -apple-system, sans-serif; max-width: 800px; margin: 0 auto; padding: 2rem; line-height: 1.5; color: #333; }
            h1 { color: #fc4c02; margin-bottom: 2rem; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; }
            .card { border: 1px solid #e1e4e8; padding: 1.5rem; border-radius: 8px; transition: all 0.2s; background: white; }
            a.card { text-decoration: none; color: inherit; }
            a.card:hover { transform: translateY(-3px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); border-color: #fc4c02; }
            h3 { margin-top: 0; color: #24292e; }
            p { color: #586069; margin-bottom: 0; }
            .status-ok { color: #28a745; font-weight: bold; }
            .status-err { color: #cb2431; font-weight: bold; }
            code { background: #f6f8fa; padding: 0.2em 0.4em; border-radius: 3px; font-size: 0.85em; }
        </style>
    </head>
    <body>
        <h1>🚴 Strava API Service</h1>
        
        <div class="grid">
            <a href="/docs" class="card">
                <h3>📚 Interactive Docs</h3>
                <p>Swagger UI for testing endpoints</p>
            </a>

            <a href="/redoc" class="card">
                <h3>📖 API Reference</h3>
                <p>Detailed documentation (ReDoc)</p>
            </a>

            <a href="https://vuhnger.dev" class="card" target="_blank">
                <h3>🎨 Frontend App</h3>
                <p>Main dashboard website</p>
            </a>

            <div class="card">
                <h3>🔌 System Status</h3>
                <div id="health-check">Connecting...</div>
            </div>
        </div>

        <div style="margin-top: 3rem; border-top: 1px solid #eee; padding-top: 1rem; color: #666; font-size: 0.9rem;">
            <p><strong>Endpoints:</strong></p>
            <ul style="list-style: none; padding-left: 0;">
                <li><code>GET /strava/stats/ytd</code> - Year-to-date stats</li>
                <li><code>GET /strava/stats/longest-run</code> - Longest run this year</li>
                <li><code>GET /strava/stats/longest-ride</code> - Longest ride this year</li>
                <li><code>GET /strava/activities</code> - Full activity history</li>
            </ul>
        </div>

        <script>
            fetch('/strava/health')
                .then(r => r.json())
                .then(data => {
                    const el = document.getElementById('health-check');
                    if(data.status === 'ok') {
                        el.innerHTML = '<span class="status-ok">● Operational</span><br><small>DB Connected</small>';
                    } else {
                        el.innerHTML = '<span class="status-err">● Degradated</span><br><small>' + data.database + '</small>';
                    }
                })
                .catch(err => {
                    document.getElementById('health-check').innerHTML = '<span class="status-err">● Unreachable</span>';
                });
        </script>
    </body>
    </html>
    """

app.include_router(router)
