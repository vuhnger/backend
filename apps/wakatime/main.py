"""
WakaTime Service API
"""

import os
import logging
import requests
from fastapi import FastAPI, APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from apps.shared.database import get_db, Base, engine, check_db_connection
from apps.shared.auth import get_api_key
from apps.shared.cors import setup_cors
from apps.shared.clickjacking_headers import setup_clickjacking_headers
from apps.shared.oauth_state import generate_state, validate_state
from apps.shared.errors import log_and_sanitize_error
from apps.wakatime.models import WakaTimeAuth, WakaTimeStats
from apps.wakatime.tasks import fetch_and_cache_wakatime_stats
from apps.shared.upsert import atomic_upsert_auth
from apps.shared.encryption import encrypt_token

logger = logging.getLogger(__name__)

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="WakaTime Service",
    version="1.0.0",
    description="WakaTime OAuth integration and cached stats",
    docs_url="/wakatime/docs",
    openapi_url="/wakatime/openapi.json",
)

# Setup CORS from shared configuration
setup_cors(app)
setup_clickjacking_headers(app)

router = APIRouter(prefix="/wakatime")


@router.get("/health")
def health():
    db_connected = check_db_connection()
    return {"status": "ok", "database": "connected" if db_connected else "disconnected"}


@router.get("/authorize")
def authorize():
    client_id = os.getenv("WAKATIME_CLIENT_ID")
    redirect_uri = os.getenv("WAKATIME_REDIRECT_URI")

    if not client_id or not redirect_uri:
        raise HTTPException(status_code=500, detail="WakaTime OAuth not configured")

    state = generate_state()
    scope = "email,read_logged_time,read_stats"

    url = (
        f"https://wakatime.com/oauth/authorize"
        f"?client_id={client_id}"
        f"&response_type=code"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scope}"
        f"&state={state}"
    )
    return RedirectResponse(url=url)


@router.get("/callback")
def oauth_callback(code: str, state: str, db: Session = Depends(get_db)):
    if not validate_state(state):
        raise HTTPException(status_code=400, detail="Invalid state")

    client_id = os.getenv("WAKATIME_CLIENT_ID")
    client_secret = os.getenv("WAKATIME_CLIENT_SECRET")
    redirect_uri = os.getenv("WAKATIME_REDIRECT_URI")

    token_url = "https://wakatime.com/oauth/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }

    try:
        response = requests.post(token_url, data=data)
        response.raise_for_status()

        try:
            token_data = response.json()
        except ValueError:
            # WakaTime sometimes returns application/x-www-form-urlencoded body
            from urllib.parse import parse_qs

            parsed = parse_qs(response.text)
            # parse_qs returns lists, we need single values
            token_data = {k: v[0] for k, v in parsed.items()}

        access_token = token_data["access_token"]
        refresh_token = token_data["refresh_token"]
        expires_at = int(
            float(token_data.get("expires_in", 3600))
        )  # Not absolute time yet?

        # Actually standard OAuth 'expires_in' is seconds from now.
        import time

        expires_at_timestamp = int(time.time()) + expires_at

        # Get user info for ID
        user_resp = requests.get(
            "https://wakatime.com/api/v1/users/current",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_resp.raise_for_status()
        user_data = user_resp.json()["data"]
        user_id = user_data["id"]

        # Store in DB
        atomic_upsert_auth(
            db=db,
            model=WakaTimeAuth,
            auth_data={
                "id": 1,
                "user_id": user_id,
                "access_token": encrypt_token(access_token),
                "refresh_token": encrypt_token(refresh_token),
                "expires_at": expires_at_timestamp,
            },
        )
        db.commit()

    except Exception as e:
        db.rollback()
        sanitized_msg, _ = log_and_sanitize_error(e, "WakaTime Auth", "Auth failed")
        raise HTTPException(status_code=500, detail=sanitized_msg)

    # Initial fetch
    try:
        fetch_and_cache_wakatime_stats()
    except Exception as e:
        logger.warning(f"Initial fetch failed: {e}")

    frontend_url = os.getenv("FRONTEND_URL", "https://vuhnger.dev")
    return RedirectResponse(url=f"{frontend_url}/?wakatime=success")


@router.post("/refresh-data")
def refresh_data(api_key: str = Depends(get_api_key)):
    fetch_and_cache_wakatime_stats()
    return {"status": "success"}


@router.get("/stats/today")
def get_today(db: Session = Depends(get_db)):
    stats = db.query(WakaTimeStats).filter(WakaTimeStats.stats_type == "today").first()
    if not stats:
        raise HTTPException(status_code=404, detail="Stats not found")
    return stats.to_dict()


@router.get("/stats/weekly")
def get_weekly(db: Session = Depends(get_db)):
    stats = (
        db.query(WakaTimeStats)
        .filter(WakaTimeStats.stats_type == "last_7_days")
        .first()
    )
    if not stats:
        raise HTTPException(status_code=404, detail="Stats not found")
    return stats.to_dict()


@router.get("/stats/all-time")
def get_all_time(db: Session = Depends(get_db)):
    stats = (
        db.query(WakaTimeStats).filter(WakaTimeStats.stats_type == "all_time").first()
    )
    if not stats:
        raise HTTPException(status_code=404, detail="Stats not found")
    return stats.to_dict()


app.include_router(router)
