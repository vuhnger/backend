"""Incremental Strava sync passes the right `after` cutoff."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import apps.strava.tasks as tasks

_LATEST = datetime(2026, 7, 1, tzinfo=UTC)


@patch("apps.strava.tasks.get_all_activities", return_value=iter([]))
def test_incremental_sync_fetches_after_latest_minus_overlap(mock_get):
    db = MagicMock()
    db.query.return_value.scalar.return_value = _LATEST
    tasks.sync_activities(db, full=False)
    assert mock_get.call_args.kwargs["after"] == _LATEST - timedelta(days=1)


@patch("apps.strava.tasks.get_all_activities", return_value=iter([]))
def test_full_sync_passes_no_cutoff(mock_get):
    db = MagicMock()
    db.query.return_value.scalar.return_value = _LATEST
    tasks.sync_activities(db, full=True)
    assert mock_get.call_args.kwargs["after"] is None


@patch("apps.strava.tasks.get_all_activities", return_value=iter([]))
def test_empty_db_does_a_full_fetch(mock_get):
    db = MagicMock()
    db.query.return_value.scalar.return_value = None  # nothing stored yet
    tasks.sync_activities(db, full=False)
    assert mock_get.call_args.kwargs["after"] is None
