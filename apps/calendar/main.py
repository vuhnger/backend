import logging
import os
import sys
from typing import Dict

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# Add parent directory to path to import shared modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.database import check_db_connection, get_db, engine, Base
from shared.auth import get_api_key
from .models import CalendarDay

logger = logging.getLogger("calendar-service")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Calendar Service",
    version="1.0.0",
    description="API for managing calendar events and scheduling",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
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

# Create database tables
Base.metadata.create_all(bind=engine)

def error_response(message: str, category: str, status_code: int) -> JSONResponse:
    """Consistent error payloads across the API."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": message,
            "category": category,
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database error on %s", request.url.path)
    return error_response(
        message="A database error occurred while processing the request.",
        category="database",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    message = (
        detail.get("message") if isinstance(detail, dict) else str(detail)
    ) or "Request failed."
    category = (
        detail.get("category") if isinstance(detail, dict) else None
    )

    if not category:
        if exc.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
            category = "security"
        elif exc.status_code >= 500:
            category = "server_error"
        else:
            category = "client_error"

    return error_response(
        message=message,
        category=category,
        status_code=exc.status_code,
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception):
    logger.exception("Unexpected error on %s", request.url.path, exc_info=exc)
    return error_response(
        message="An unexpected server error occurred. Please try again later.",
        category="server_error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )

# Router setup
router = APIRouter(prefix="/calendar")

@router.get("/health")
def health():
    """Health check endpoint - returns service status and database connectivity"""
    db_connected = check_db_connection()

    return {
        "status": "ok" if db_connected else "degraded",
        "service": "calendar",
        "database": "connected" if db_connected else "disconnected"
    }


@router.get("/days", response_model=Dict[str, dict])
def get_all_days(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Get all advent calendar days
    Returns: Dictionary with day numbers as keys
    Requires: X-API-Key header
    """
    days = db.query(CalendarDay).all()

    # Convert to dictionary format matching frontend expectations
    result = {}
    for day in days:
        result[str(day.day)] = day.to_dict()

    return result


@router.get("/days/{day_number}")
def get_day(
    day_number: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Get a specific advent calendar day

    Args:
        day_number: Day number (1-24)

    Returns: Day data
    Requires: X-API-Key header
    """
    if day_number < 1 or day_number > 24:
        raise HTTPException(status_code=400, detail="Day must be between 1 and 24")

    day = db.query(CalendarDay).filter(CalendarDay.day == day_number).first()

    if not day:
        raise HTTPException(status_code=404, detail=f"Day {day_number} not found")

    return day.to_dict()


@router.post("/seed")
def seed_calendar_data(
    calendar_data: Dict[str, dict],
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Seed the database with calendar data

    Request body should be your JSON data with day numbers as keys
    Requires: X-API-Key header

    Example:
    {
      "1": { "type": "text", "title": "...", "body": "..." },
      "2": { "type": "code", ... }
    }
    """
    count = 0

    for day_str, day_data in calendar_data.items():
        day_number = int(day_str)

        # Extract type and remaining data
        day_type = day_data.pop("type")

        # Check if day already exists
        existing = db.query(CalendarDay).filter(CalendarDay.day == day_number).first()

        if existing:
            # Update existing
            existing.type = day_type
            existing.data = day_data
        else:
            # Create new
            new_day = CalendarDay(
                day=day_number,
                type=day_type,
                data=day_data
            )
            db.add(new_day)

        count += 1

    db.commit()

    return {
        "message": f"Successfully seeded {count} days",
        "days": count
    }


app.include_router(router)
