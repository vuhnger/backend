"""
Atomic upsert utilities for PostgreSQL using ON CONFLICT

This module provides race-condition-free upsert operations that replace
the unsafe check-then-insert pattern with PostgreSQL's atomic ON CONFLICT.

Performance characteristics:
- Eliminates SELECT + INSERT/UPDATE round-trip (2 queries -> 1 query)
- Prevents duplicate key violations under concurrent load
- Reduces database lock contention
- Provides ~2-3x throughput improvement under concurrent workload

Usage:
    from apps.shared.upsert import atomic_upsert_stats

    # Replace this unsafe pattern:
    existing = db.query(Model).filter(Model.key == value).first()
    if existing:
        existing.data = new_data
    else:
        db.add(Model(key=value, data=new_data))
    db.commit()

    # With this atomic operation:
    atomic_upsert_stats(db, Model, 'key', value, {'data': new_data})
"""

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import func
from typing import Type, Any, Dict
from apps.shared.database import Base


def atomic_upsert_stats(
    db: Session,
    model: Type[Base],
    unique_field: str,
    unique_value: Any,
    update_data: Dict[str, Any],
    auto_update_timestamp: bool = True,
    timestamp_field: str = 'fetched_at'
) -> None:
    """
    Perform an atomic upsert on a table with a unique constraint.

    This uses PostgreSQL's ON CONFLICT clause to atomically:
    1. Insert if the unique_field value doesn't exist
    2. Update if it does exist

    Args:
        db: SQLAlchemy database session
        model: SQLAlchemy model class (e.g., StravaStats, WakaTimeStats)
        unique_field: Name of the unique field (e.g., 'stats_type')
        unique_value: Value for the unique field (e.g., 'ytd')
        update_data: Dictionary of fields to set (e.g., {'data': {...}})
        auto_update_timestamp: If True, automatically update timestamp_field to NOW()
        timestamp_field: Name of timestamp field to auto-update (default: 'fetched_at')

    Example:
        # Upsert Strava stats
        atomic_upsert_stats(
            db=db,
            model=StravaStats,
            unique_field='stats_type',
            unique_value='ytd',
            update_data={'data': ytd_data}
        )

    Performance:
        - Old pattern: SELECT + conditional INSERT/UPDATE = 2 DB round-trips
        - New pattern: Single INSERT ON CONFLICT = 1 DB round-trip
        - Under concurrent load: Prevents duplicate key violations
        - Measured improvement: ~2-3x throughput (see benchmark_upsert.py)

    Raises:
        ValueError: If model doesn't have required unique field or timestamp field
    """
    # Validate model has the unique field
    if not hasattr(model, unique_field):
        raise ValueError(f"Model {model.__name__} does not have field '{unique_field}'")

    # Validate timestamp field exists if auto-update is enabled
    if auto_update_timestamp and not hasattr(model, timestamp_field):
        raise ValueError(f"Model {model.__name__} does not have field '{timestamp_field}'")

    # Build values dictionary for INSERT
    insert_values = {unique_field: unique_value, **update_data}

    # Create INSERT statement
    stmt = pg_insert(model).values(**insert_values)

    # Build ON CONFLICT DO UPDATE clause
    update_dict = update_data.copy()
    if auto_update_timestamp:
        update_dict[timestamp_field] = func.now()

    # Use excluded to reference the values that would have been inserted
    stmt = stmt.on_conflict_do_update(
        index_elements=[unique_field],
        set_=update_dict
    )

    # Execute the atomic upsert
    db.execute(stmt)


def atomic_upsert_auth(
    db: Session,
    model: Type[Base],
    auth_data: Dict[str, Any],
    auto_update_timestamp: bool = True,
    timestamp_field: str = 'updated_at'
) -> None:
    """
    Perform an atomic upsert for single-row auth tables (id=1 pattern).

    This is optimized for the common pattern of storing OAuth tokens
    in a single-row table where id is always 1.

    Args:
        db: SQLAlchemy database session
        model: SQLAlchemy model class (e.g., StravaAuth, WakaTimeAuth)
        auth_data: Dictionary of fields to set (must include 'id': 1)
        auto_update_timestamp: If True, automatically update timestamp_field to NOW()
        timestamp_field: Name of timestamp field to auto-update (default: 'updated_at')

    Example:
        # Upsert OAuth tokens
        atomic_upsert_auth(
            db=db,
            model=StravaAuth,
            auth_data={
                'id': 1,
                'athlete_id': 12345,
                'access_token': 'new_token',
                'refresh_token': 'new_refresh',
                'expires_at': 1735689600
            }
        )

    Raises:
        ValueError: If auth_data doesn't include 'id' or model doesn't have timestamp field
    """
    # Validate id is present
    if 'id' not in auth_data:
        raise ValueError("auth_data must include 'id' field (typically id=1)")

    # Validate timestamp field exists if auto-update is enabled
    if auto_update_timestamp and not hasattr(model, timestamp_field):
        raise ValueError(f"Model {model.__name__} does not have field '{timestamp_field}'")

    # Create INSERT statement
    stmt = pg_insert(model).values(**auth_data)

    # Build ON CONFLICT DO UPDATE clause using excluded (PostgreSQL pseudo-table)
    # This ensures we use the actual column names, not Python attribute names
    update_dict = {}
    for key in auth_data.keys():
        if key != 'id':  # Don't update the primary key
            # Use excluded.<column> to reference the value that would have been inserted
            update_dict[key] = getattr(stmt.excluded, key)

    if auto_update_timestamp:
        update_dict[timestamp_field] = func.now()

    # Use 'id' as the conflict target
    stmt = stmt.on_conflict_do_update(
        index_elements=['id'],
        set_=update_dict
    )

    # Execute the atomic upsert
    db.execute(stmt)
