"""
Database configuration and session management

This module provides the basic SQLAlchemy setup for database connectivity.
NO models are defined here - this is just infrastructure.
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

# Get database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable must be set. "
        "Example: postgresql+psycopg2://user:password@host:5432/database"
    )


def _int_env(name: str, default: int) -> int:
    """Read a positive-int tuning knob from the environment, falling back safely."""
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# Create engine with SQLAlchemy's default QueuePool instead of NullPool.
# NullPool opened a fresh TCP + auth handshake on every request; a real pool keeps
# a small set of warm connections, which is the single biggest per-request win here.
#   - pool_pre_ping: cheaply validate a connection before use, so a Postgres
#     restart or an idle-timeout drop surfaces as a transparent reconnect instead
#     of the first query after the gap failing.
#   - pool_recycle: proactively retire connections older than this (seconds) to
#     stay under server-side / proxy idle limits.
# All knobs are env-overridable so a low-memory host can shrink the pool.
engine = create_engine(
    DATABASE_URL,
    pool_size=_int_env("DB_POOL_SIZE", 5),
    max_overflow=_int_env("DB_MAX_OVERFLOW", 10),
    pool_timeout=_int_env("DB_POOL_TIMEOUT", 30),
    pool_recycle=_int_env("DB_POOL_RECYCLE", 1800),
    pool_pre_ping=True,
    echo=False,  # Set to True for SQL query logging during development
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
# Models will inherit from this when implemented
Base = declarative_base()


def get_db():
    """
    Dependency injection for database sessions
    Usage in FastAPI endpoints:

    @app.get("/endpoint")
    def endpoint(db: Session = Depends(get_db)):
        # use db here
        pass
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> bool:
    """
    Test database connectivity
    Returns True if connection successful, False otherwise
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
