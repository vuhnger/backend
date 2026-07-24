from unittest.mock import MagicMock, patch

from apps.wakatime.tasks import fetch_and_cache_wakatime_stats
from apps.wakatime.models import WakaTimeAuth


@patch("apps.wakatime.tasks.atomic_upsert_stats")
@patch("apps.wakatime.tasks.get_stats")
@patch("apps.wakatime.tasks.get_weekly_summary")
@patch("apps.wakatime.tasks.get_today_summary")
@patch("apps.wakatime.tasks.SessionLocal")
def test_fetch_and_cache_wakatime_stats(
    mock_session_local, mock_today, mock_weekly, mock_stats, mock_upsert
):
    # Arrange: a session whose auth lookup returns an existing row.
    mock_session = MagicMock()
    mock_session_local.return_value = mock_session
    mock_session.query.return_value.first.return_value = WakaTimeAuth(
        id=1, user_id="test"
    )

    mock_today.return_value = {"grand_total": {"total_seconds": 3600}}
    mock_weekly.return_value = {"languages": []}
    mock_stats.return_value = {"total_seconds": 100000}

    # Act
    fetch_and_cache_wakatime_stats()

    # Assert: each source is fetched exactly once (all_time via get_stats).
    mock_today.assert_called_once()
    mock_weekly.assert_called_once()
    mock_stats.assert_called_once_with(mock_session, "all_time")

    # Three cache writes, in order, keyed today / last_7_days / all_time.
    assert mock_upsert.call_count == 3
    unique_values = [c.kwargs["unique_value"] for c in mock_upsert.call_args_list]
    assert unique_values == ["today", "last_7_days", "all_time"]

    # The "today" payload is passed through and tagged with its range label.
    today_data = mock_upsert.call_args_list[0].kwargs["update_data"]["data"]
    assert today_data["grand_total"] == {"total_seconds": 3600}
    assert today_data["range"] == "today"

    assert mock_session.commit.called
