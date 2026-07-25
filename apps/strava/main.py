"""
Strava Service API

OAuth integration for Strava with cached statistics.
Single user mode - stores one set of tokens and serves cached data.
"""

import hashlib
import hmac
import logging
import secrets
from collections import OrderedDict
from datetime import datetime
from threading import Lock

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy import desc, extract, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from apps.shared.app_factory import create_app, include_versioned
from apps.shared.auth import get_api_key
from apps.shared.config import settings
from apps.shared.database import check_db_connection, get_db
from apps.shared.errors import log_and_sanitize_error
from apps.shared.oauth_owner import enforce_owner
from apps.shared.oauth_state import generate_state, validate_state
from apps.strava.client_factory import strava_client
from apps.strava.geometry import HEATMAP_CELL_SIZE_M, build_heatmap
from apps.strava.models import StravaActivity, StravaAuth, StravaStats
from apps.strava.tasks import fetch_and_cache_stats

logger = logging.getLogger(__name__)

# Bump when the shape or the derivation of /strava/heatmap changes, so every
# cached copy revalidates instead of serving a grid built by older rules.
HEATMAP_PAYLOAD_VERSION = "1"

# Cached hard, because the aggregate is almost entirely immutable: a finished
# run's track never changes, so only a newly logged activity can move it, and
# that just adds counts. An hour of staleness on the newest run is a fair price
# for the frontend usually paying nothing at all. `stale-while-revalidate` then
# lets a shared cache serve the old copy instantly while it refreshes in the
# background, so even revalidation never lands in the client's 5 s budget.
HEATMAP_CACHE_CONTROL = "public, max-age=3600, stale-while-revalidate=86400"

# ETag key. The tag commits to the home coordinate and privacy radius so a config
# change invalidates every cached response — but those are low-entropy values, and
# a plain digest of them could be brute-forced back out of a public header. Keying
# the digest with a server secret makes that impossible. Falls back to a
# per-process random key when no secret is configured: ETags then reset on
# restart, which costs a revalidation and leaks nothing.
_ETAG_KEY = (settings.state_secret or secrets.token_urlsafe(32)).encode()

# Aggregating every track is the one genuinely expensive thing this service
# does, and the ETag already captures exactly what the result depends on — so it
# doubles as the cache key: if the tag matches, the cached body is valid by
# construction. A handful of entries covers the realistic query variants
# (all types, Run, Ride) across a config change.
#
# A lock rather than a bare dict because sync endpoints run in a threadpool and
# OrderedDict.move_to_end is not atomic.
_HEATMAP_CACHE: OrderedDict[str, dict] = OrderedDict()
_HEATMAP_CACHE_MAX = 8
_HEATMAP_CACHE_LOCK = Lock()


def _heatmap_cache_get(etag: str) -> dict | None:
    with _HEATMAP_CACHE_LOCK:
        payload = _HEATMAP_CACHE.get(etag)
        if payload is not None:
            _HEATMAP_CACHE.move_to_end(etag)
        return payload


def _heatmap_cache_put(etag: str, payload: dict) -> None:
    with _HEATMAP_CACHE_LOCK:
        _HEATMAP_CACHE[etag] = payload
        _HEATMAP_CACHE.move_to_end(etag)
        while len(_HEATMAP_CACHE) > _HEATMAP_CACHE_MAX:
            _HEATMAP_CACHE.popitem(last=False)

# Schema is managed by Alembic migrations (`alembic upgrade head`), not created
# at import time. See alembic/ and `make migrate`.

app = create_app(
    title="Strava Service",
    url_prefix="strava",
    description="Strava OAuth integration with cached activity statistics",
)

# Router setup
router = APIRouter(prefix="/strava")


@app.get("/", response_class=FileResponse)
def landing_page():
    return FileResponse("static/index.html")


@router.get("/health")
def health():
    """Health check endpoint"""
    db_connected = check_db_connection()
    return {
        "status": "ok" if db_connected else "degraded",
        "service": "strava",
        "database": "connected" if db_connected else "disconnected",
    }


@router.get("/authorize")
def authorize():
    """
    Initiate OAuth flow by redirecting to Strava.
    User will be redirected to Strava to authorize the app.
    """
    client_id = settings.strava_client_id
    redirect_uri = settings.strava_redirect_uri

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
def oauth_callback(
    code: str,
    state: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    OAuth callback endpoint.
    Strava redirects here after user authorizes.
    Exchanges code for tokens and stores in database.
    """
    # Verify state for CSRF protection
    if not validate_state(state):
        raise HTTPException(
            status_code=400, detail="Invalid or expired state parameter"
        )

    client_id = settings.strava_client_id
    client_secret = settings.strava_client_secret

    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Strava OAuth not configured")

    try:
        # Exchange code for tokens
        client = strava_client()
        token_response = client.exchange_code_for_token(
            client_id=client_id, client_secret=client_secret, code=code
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

        # This endpoint is public, so the account behind the exchange has to be
        # checked before it can replace the stored grant.
        enforce_owner(
            db=db,
            model=StravaAuth,
            id_field="athlete_id",
            incoming_id=athlete_id,
            configured_owner=settings.strava_owner_athlete_id,
            provider="strava",
        )

        # Store in database (single user, id=1) using atomic upsert
        from apps.shared.encryption import encrypt_token
        from apps.shared.upsert import atomic_upsert_auth

        # Encrypt tokens before storing (use database column names)
        atomic_upsert_auth(
            db=db,
            model=StravaAuth,
            auth_data={
                "id": 1,
                "athlete_id": athlete_id,
                "access_token": encrypt_token(access_token),
                "refresh_token": encrypt_token(refresh_token),
                "expires_at": expires_at,
            },
        )
        db.commit()
    except HTTPException:
        # A deliberate rejection (e.g. wrong account) must reach the caller as
        # itself, not be reshaped into a 500 by the handler below.
        db.rollback()
        raise
    except Exception as e:
        # Rollback any pending database changes to maintain session consistency
        db.rollback()
        sanitized_msg, error_id = log_and_sanitize_error(
            e, "OAuth token exchange", "OAuth authorization failed. Please try again."
        )
        raise HTTPException(status_code=500, detail=sanitized_msg)

    # Fetch initial data AFTER the response is sent, so the OAuth redirect
    # returns immediately instead of blocking on a full Strava sync.
    background_tasks.add_task(fetch_and_cache_stats)

    # Redirect to frontend success page
    frontend_url = settings.frontend_url or "https://vuhnger.dev"
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
            status_code=404, detail="YTD stats not cached yet. Try /strava/refresh-data"
        )

    return stats.to_dict()


@router.get("/stats/activities")
def get_activities(db: Session = Depends(get_db)):
    """
    Get cached recent activities (last 30).
    Returns list of activities with basic info.
    """
    stats = (
        db.query(StravaStats)
        .filter(StravaStats.stats_type == "recent_activities")
        .first()
    )

    if not stats:
        raise HTTPException(
            status_code=404,
            detail="Activities not cached yet. Try /strava/refresh-data",
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
            detail="Monthly stats not cached yet. Try /strava/refresh-data",
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
            extract("year", StravaActivity.start_date_local) == year,
        )
        .order_by(desc(StravaActivity.distance))
        .first()
    )

    if not longest_run:
        raise HTTPException(
            status_code=404,
            detail=f"No runs found for year {year}. Try /strava/refresh-data",
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
            extract("year", StravaActivity.start_date_local) == year,
        )
        .order_by(desc(StravaActivity.distance))
        .first()
    )

    if not longest_ride:
        raise HTTPException(
            status_code=404,
            detail=f"No rides found for year {year}. Try /strava/refresh-data",
        )

    return longest_ride.to_dict()


@router.get("/stats/totals")
def get_all_time_totals(db: Session = Depends(get_db)):
    """
    Get all-time totals for each activity type.
    """
    results = (
        db.query(
            StravaActivity.type,
            func.count(StravaActivity.id).label("count"),
            func.sum(StravaActivity.distance).label("distance"),
            func.sum(StravaActivity.moving_time).label("moving_time"),
            func.sum(StravaActivity.total_elevation_gain).label("elevation_gain"),
        )
        .group_by(StravaActivity.type)
        .all()
    )

    return {
        "type": "all_time_totals",
        "data": {
            r.type: {
                "count": r.count,
                "distance": float(r.distance) if r.distance else 0,
                "moving_time": int(r.moving_time) if r.moving_time else 0,
                "elevation_gain": float(r.elevation_gain) if r.elevation_gain else 0,
            }
            for r in results
        },
        "fetched_at": datetime.now().isoformat(),
    }


@router.get("/stats/yearly")
def get_yearly_stats(db: Session = Depends(get_db)):
    """
    Get activity totals grouped by year and type.
    """
    year_col = extract("year", StravaActivity.start_date_local)

    results = (
        db.query(
            year_col.label("year"),
            StravaActivity.type,
            func.count(StravaActivity.id).label("count"),
            func.sum(StravaActivity.distance).label("distance"),
            func.sum(StravaActivity.moving_time).label("moving_time"),
            func.sum(StravaActivity.total_elevation_gain).label("elevation_gain"),
        )
        .group_by(year_col, StravaActivity.type)
        .order_by(desc("year"), StravaActivity.type)
        .all()
    )

    data = {}
    for r in results:
        year_str = str(int(r.year))
        if year_str not in data:
            data[year_str] = {}

        data[year_str][r.type] = {
            "count": r.count,
            "distance": float(r.distance) if r.distance else 0,
            "moving_time": int(r.moving_time) if r.moving_time else 0,
            "elevation_gain": float(r.elevation_gain) if r.elevation_gain else 0,
        }

    return {
        "type": "yearly_stats",
        "data": data,
        "fetched_at": datetime.now().isoformat(),
    }


@router.get("/activities")
def get_all_activities_endpoint(
    limit: int = Query(100, ge=1, le=200, description="Max rows to return (capped at 200)."),
    offset: int = Query(0, ge=0),
    year: int = None,
    activity_type: str = None,
    db: Session = Depends(get_db),
):
    """
    Get all activities from history with pagination and filtering.

    `limit` is capped at 200 so a client can't request an unbounded result set.
    """
    query = db.query(StravaActivity).order_by(desc(StravaActivity.start_date))

    if year:
        query = query.filter(extract("year", StravaActivity.start_date_local) == year)

    if activity_type:
        query = query.filter(StravaActivity.type == activity_type)

    total = query.count()
    activities = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [a.to_dict() for a in activities],
    }


def _weak_etag(*parts: object) -> str:
    """Build a weak, secret-keyed ETag from the values a response depends on.

    Weak (`W/`) because gzip means the same resource ships as more than one byte
    sequence; a strong tag is supposed to identify exact bytes. Weak is what
    cache revalidation needs anyway — it asserts semantic equivalence.
    """
    payload = "|".join(str(p) for p in parts).encode()
    digest = hmac.new(_ETAG_KEY, payload, hashlib.sha256).hexdigest()[:32]
    return f'W/"{digest}"'


def _strip_weak(tag: str) -> str:
    return tag[2:] if tag.startswith("W/") else tag


def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    """RFC 9110 If-None-Match check: comma-separated list, `*`, weak `W/` prefix.

    Both sides are normalised — comparing a `W/`-prefixed tag against stripped
    candidates would never match, and the endpoint would answer 200 forever.
    """
    if not if_none_match:
        return False
    candidates = [c.strip() for c in if_none_match.split(",")]
    if "*" in candidates:
        return True
    return _strip_weak(etag) in {_strip_weak(c) for c in candidates}


@router.get("/heatmap")
def get_heatmap(
    request: Request,
    activity_type: str | None = Query(None, max_length=50, description="e.g. Run; omit for all types."),
    db: Session = Depends(get_db),
):
    """Aggregated heat grid over every GPS-recorded activity, all years.

    Returns:

        {
          "cell_size_m": 15,
          "bounds": [min_lng, min_lat, max_lng, max_lat],   // null when empty
          "max_count": 87,
          "activity_count": 512,
          "total_distance_m": 4210000,
          "cells": [[lng, lat, count], ...]
        }

    `cells` are `[lng, lat, count]` triples rather than objects — with hundreds
    of thousands of cells, repeated key names would dominate the payload. Four
    decimals resolve to ~11 m, finer than the 15 m cell.

    `count` is how many *activities* touched a cell, not how many GPS samples
    landed in it. Sample density tracks pace, so counting samples would highlight
    where the running is slowest rather than where it is most frequent.

    `activity_count` and `total_distance_m` describe every activity matching the
    filter, including ones without GPS; the cells necessarily derive only from
    the subset that has a track.

    Privacy: each track is clipped against the configured home coordinate before
    aggregation (apps/strava/geometry.clip_home_area), and the aggregate itself
    carries no timestamps, activity IDs, or point ordering — individual runs
    cannot be reconstructed from it. Neither the home coordinate nor the radius
    appears in the response. If the coordinate is unconfigured this returns 503
    rather than aggregate unclipped tracks: absence of config must never degrade
    into absence of privacy.

    Status codes are meaningful: 200 with `cells: []` means the filter matched
    nothing (or nothing had GPS), while 503 means nothing has been synced yet,
    the database is unreachable, or the privacy clipping is unconfigured.
    """
    home = settings.strava_home_coordinate
    if home is None:
        logger.error(
            "Refusing to serve heatmap: STRAVA_HOME_LAT/STRAVA_HOME_LNG are not configured"
        )
        raise HTTPException(
            status_code=503,
            detail="Heatmap is unavailable: privacy clipping is not configured.",
        )
    radius_m = settings.strava_privacy_radius_m

    try:
        query = db.query(StravaActivity)
        if activity_type:
            query = query.filter(StravaActivity.type == activity_type)

        # One pass for the summary figures and the cache validator.
        # `max(fetched_at)` over the filtered set changes exactly when one of
        # these rows is re-synced, which is the only way the aggregate can move.
        activity_count, total_distance, last_synced = query.with_entities(
            func.count(StravaActivity.id),
            func.coalesce(func.sum(StravaActivity.distance), 0.0),
            func.max(StravaActivity.fetched_at),
        ).one()

        if activity_count == 0 and db.query(StravaActivity.id).first() is None:
            raise HTTPException(
                status_code=503,
                detail="Activity data has not been synced yet. Try again shortly.",
            )

        etag = _weak_etag(
            HEATMAP_PAYLOAD_VERSION,
            activity_type,
            HEATMAP_CELL_SIZE_M,
            home[0],
            home[1],
            radius_m,
            activity_count,
            total_distance,
            last_synced,
        )
        headers = {"ETag": etag, "Cache-Control": HEATMAP_CACHE_CONTROL}

        if _etag_matches(request.headers.get("if-none-match"), etag):
            return Response(status_code=304, headers=headers)

        cached = _heatmap_cache_get(etag)
        if cached is not None:
            return JSONResponse(content=cached, headers=headers)

        # Only the polyline column — the rest of the row is dead weight when
        # hundreds of activities are being aggregated.
        polylines = [row[0] for row in query.with_entities(StravaActivity.summary_polyline).all()]
    except SQLAlchemyError as e:
        sanitized_msg, _ = log_and_sanitize_error(
            e, "Heatmap query", "Heatmap is temporarily unavailable"
        )
        raise HTTPException(status_code=503, detail=sanitized_msg)

    grid = build_heatmap(polylines, home, radius_m)
    payload = {
        "cell_size_m": HEATMAP_CELL_SIZE_M,
        "bounds": grid["bounds"],
        "max_count": grid["max_count"],
        "activity_count": activity_count,
        "total_distance_m": round(float(total_distance)),
        "cells": grid["cells"],
    }
    _heatmap_cache_put(etag, payload)

    # No response_model: pydantic would re-validate hundreds of thousands of
    # numbers per request for no gain. The shape is built in one place here and
    # covered by tests instead.
    return JSONResponse(content=payload, headers=headers)


@router.post("/refresh-data")
def refresh_data(full: bool = False, api_key: str = Depends(get_api_key)):
    """
    Manually trigger data refresh from Strava.
    Protected endpoint - requires X-API-Key header.

    Pass `?full=true` to force a full re-sync of all history instead of the
    default incremental sync.
    """
    try:
        fetch_and_cache_stats(full=full)
        return {"status": "success", "message": "Data refreshed successfully"}
    except Exception as e:
        sanitized_msg, error_id = log_and_sanitize_error(
            e, "Data refresh", "Failed to refresh Strava data"
        )
        raise HTTPException(status_code=500, detail=sanitized_msg)


include_versioned(app, router)
