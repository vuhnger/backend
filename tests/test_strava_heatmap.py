"""Heatmap aggregation: polyline decoding, home clipping, gridding, and /strava/heatmap.

The clipping and aggregation tests are the important ones — they are what stands
between the home address and a public page.
"""

import gzip
import math
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from apps.shared.config import settings
from apps.shared.database import get_db
from apps.strava.geometry import (
    CELL_COORD_PRECISION,
    HEATMAP_CELL_SIZE_M,
    METERS_PER_DEGREE_LAT,
    build_heatmap,
    clip_home_area,
    decode_polyline,
    grid_steps,
    track_cells,
)
from apps.strava.main import _strip_weak, app

# Google's documented reference polyline; decodes to three known coordinates.
REFERENCE_POLYLINE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
REFERENCE_COORDS = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]

HOME = (59.9139, 10.7522)


def _encode(coords, precision=5):
    """Minimal polyline encoder — test-side only, for building fixtures.

    Deliberately not imported from the app: production only ever decodes, and a
    shared implementation would let a codec bug cancel itself out in these tests.
    """
    factor = 10**precision
    out = []
    prev_lat = prev_lng = 0
    for lat, lng in coords:
        ilat, ilng = round(lat * factor), round(lng * factor)
        for delta in (ilat - prev_lat, ilng - prev_lng):
            v = ~(delta << 1) if delta < 0 else (delta << 1)
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        prev_lat, prev_lng = ilat, ilng
    return "".join(out)


def _offset_point(home, north_m=0.0, east_m=0.0):
    """A coordinate a given number of metres from `home` (flat-earth is fine here)."""
    lat = home[0] + north_m / METERS_PER_DEGREE_LAT
    lng = home[1] + east_m / (METERS_PER_DEGREE_LAT * math.cos(math.radians(home[0])))
    return (lat, lng)


def _metres_from_home(lat, lng):
    dy = (lat - HOME[0]) * METERS_PER_DEGREE_LAT
    dx = (lng - HOME[1]) * METERS_PER_DEGREE_LAT * math.cos(math.radians(HOME[0]))
    return math.hypot(dx, dy)


# --- polyline decoding ------------------------------------------------------


def test_decode_matches_reference_polyline():
    decoded = decode_polyline(REFERENCE_POLYLINE)
    assert len(decoded) == 3
    for got, want in zip(decoded, REFERENCE_COORDS, strict=True):
        assert got[0] == pytest.approx(want[0], abs=1e-5)
        assert got[1] == pytest.approx(want[1], abs=1e-5)


@pytest.mark.parametrize("bad", ["_p~iF~ps|U_ulL", "\x00\x01", "~~~~~~~~~~~~"])
def test_decode_rejects_malformed_input(bad):
    with pytest.raises(ValueError):
        decode_polyline(bad)


@pytest.mark.parametrize("char", ["ÿ", "", "€"])
def test_decode_rejects_characters_above_the_encoding_range(char):
    # The format only uses ASCII 63..126. Higher code points used to slip past
    # the sign check and contribute junk bits, decoding into a plausible-looking
    # but entirely fabricated route.
    with pytest.raises(ValueError):
        decode_polyline(REFERENCE_POLYLINE + char)


# --- extraction from Strava's own models ------------------------------------


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"map": {"id": "a", "summary_polyline": REFERENCE_POLYLINE}}, REFERENCE_POLYLINE),
        ({"map": {"id": "a", "summary_polyline": ""}}, None),  # treadmill: no GPS
        ({}, None),                                            # manual entry: no map at all
    ],
)
def test_polyline_is_read_off_the_list_response(payload, expected):
    # Validated against a real stravalib SummaryActivity, not a stub: this is the
    # seam a stravalib upgrade could rename underneath us, and the failure mode
    # would be silent (an empty heatmap) rather than an exception.
    from stravalib.model import SummaryActivity

    from apps.strava.client import _summary_polyline

    activity = SummaryActivity.model_validate({"id": 1, "name": "Run", **payload})
    assert _summary_polyline(activity) == expected


# --- clipping (privacy-critical) --------------------------------------------


def test_clips_points_inside_radius_at_both_ends():
    track = [
        _offset_point(HOME, north_m=0),      # at home
        _offset_point(HOME, north_m=200),    # inside 500 m
        _offset_point(HOME, north_m=900),    # outside
        _offset_point(HOME, north_m=1500),   # outside
        _offset_point(HOME, north_m=300),    # inside again, on the way back
    ]
    assert clip_home_area(track, HOME, 500.0) == track[2:4]


def test_clips_points_that_pass_home_mid_route():
    # A run that goes out, past the house, and out again. The middle points must
    # go too — leaving them would expose the address just as plainly as the ends.
    track = [
        _offset_point(HOME, north_m=2000),
        _offset_point(HOME, north_m=100),    # inside
        _offset_point(HOME, north_m=-2000),
    ]
    kept = clip_home_area(track, HOME, 500.0)
    assert kept == [track[0], track[2]]


def test_clipping_is_radial_not_just_north_south():
    # An east-west run past the door must be clipped too; a latitude-only check
    # would sail straight through.
    track = [_offset_point(HOME, east_m=d) for d in (0, 100, 300, 900)]
    kept = clip_home_area(track, HOME, 500.0)
    assert len(kept) == 1
    assert _metres_from_home(*kept[0]) > 500.0


def test_route_entirely_inside_radius_yields_no_points():
    track = [_offset_point(HOME, north_m=d) for d in (0, 100, 200, 100, 0)]
    assert clip_home_area(track, HOME, 500.0) == []


def test_radius_is_honoured():
    track = [_offset_point(HOME, north_m=d) for d in (0, 700, 1400)]
    assert len(clip_home_area(track, HOME, 500.0)) == 2   # only the home point goes
    assert len(clip_home_area(track, HOME, 1000.0)) == 1  # 700 m now excluded too


def test_clip_rejects_non_positive_radius():
    # A zero radius would silently disable clipping; refuse rather than no-op.
    with pytest.raises(ValueError):
        clip_home_area([(0.0, 0.0)], HOME, 0.0)


def test_clipping_handles_a_home_near_the_antimeridian():
    # 179.999E and 179.999W are ~200 m apart, not ~360 degrees. Treating the raw
    # difference as the distance would keep a point right next to the house.
    home = (0.0, 179.999)
    just_across = (0.0, -179.999)
    assert clip_home_area([just_across], home, 500.0) == []
    # A genuinely distant point at the same latitude still survives.
    assert clip_home_area([(0.0, 179.98)], home, 500.0) == [(0.0, 179.98)]


# --- gridding ---------------------------------------------------------------


def test_grid_cells_are_roughly_square_in_metres():
    lat_step, lng_step = grid_steps(HEATMAP_CELL_SIZE_M, HOME[0])
    height_m = lat_step * METERS_PER_DEGREE_LAT
    width_m = lng_step * METERS_PER_DEGREE_LAT * math.cos(math.radians(HOME[0]))
    assert height_m == pytest.approx(HEATMAP_CELL_SIZE_M, rel=0.01)
    # Without the cos(lat) correction this would be ~2x too wide at 60°N.
    assert width_m == pytest.approx(HEATMAP_CELL_SIZE_M, rel=0.01)


def test_nearby_points_collapse_into_one_cell():
    lat_step, lng_step = grid_steps(HEATMAP_CELL_SIZE_M, HOME[0])
    # Three samples a couple of metres apart — one cell, not three.
    track = [_offset_point(HOME, north_m=1000 + d) for d in (0, 2, 4)]
    assert len(track_cells(track, lat_step, lng_step)) == 1


def test_distant_points_land_in_different_cells():
    lat_step, lng_step = grid_steps(HEATMAP_CELL_SIZE_M, HOME[0])
    track = [_offset_point(HOME, north_m=1000 + d) for d in (0, 60, 120)]
    assert len(track_cells(track, lat_step, lng_step)) == 3


def test_emitted_precision_does_not_merge_distinct_cells():
    # 4 decimals must resolve finer than the cell, or neighbouring cells would
    # collapse and counts would silently merge.
    lat_step, _ = grid_steps(HEATMAP_CELL_SIZE_M, HOME[0])
    assert lat_step > 10**-CELL_COORD_PRECISION


# --- aggregation ------------------------------------------------------------


def _track_polyline(north_range, east_m=0.0):
    return _encode([_offset_point(HOME, north_m=d, east_m=east_m) for d in north_range])


def test_counts_are_per_activity_not_per_gps_sample():
    # One activity that dawdles (many samples in one cell) must contribute 1,
    # not 20 — otherwise the map highlights where the running is slowest.
    dawdling = _encode([_offset_point(HOME, north_m=1000 + d * 0.1) for d in range(20)])
    grid = build_heatmap([dawdling], HOME, 500.0)
    assert grid["max_count"] == 1
    assert len(grid["cells"]) == 1


def test_repeated_route_accumulates_counts():
    track = _track_polyline(range(600, 1200, 10))
    grid = build_heatmap([track] * 5, HOME, 500.0)
    assert grid["max_count"] == 5
    assert grid["gps_activity_count"] == 5
    assert all(cell[2] == 5 for cell in grid["cells"])


def test_aggregate_excludes_the_home_area():
    grid = build_heatmap([_track_polyline(range(0, 3000, 10))], HOME, 500.0)
    assert grid["cells"]
    for lng, lat, _count in grid["cells"]:
        assert _metres_from_home(lat, lng) > 500.0


def test_no_emitted_cell_footprint_overlaps_the_exclusion_circle():
    # Clipping filters points, but snapping then shifts each survivor by up to
    # half a cell diagonal — so a point legally outside the radius could produce
    # a cell centred inside it. Approach the boundary from every direction at
    # 1 m resolution and assert the whole cell, not just its centre, stays out.
    radius = 500.0
    tracks = []
    for bearing in range(0, 360, 5):
        rad = math.radians(bearing)
        tracks.append(
            _encode([
                _offset_point(HOME, north_m=d * math.cos(rad), east_m=d * math.sin(rad))
                for d in range(400, 700)
            ])
        )

    grid = build_heatmap(tracks, HOME, radius)
    assert grid["cells"], "the fixture should still produce cells further out"

    cell_reach = HEATMAP_CELL_SIZE_M * math.sqrt(2) / 2
    for lng, lat, _count in grid["cells"]:
        assert _metres_from_home(lat, lng) >= radius + cell_reach


def test_bounds_enclose_every_cell():
    grid = build_heatmap(
        [_track_polyline(range(600, 2000, 10)), _track_polyline(range(600, 2000, 10), east_m=800)],
        HOME,
        500.0,
    )
    min_lng, min_lat, max_lng, max_lat = grid["bounds"]
    for lng, lat, _count in grid["cells"]:
        assert min_lng <= lng <= max_lng
        assert min_lat <= lat <= max_lat


def test_activities_without_gps_are_skipped_not_counted():
    grid = build_heatmap([None, "", _track_polyline(range(600, 1200, 10))], HOME, 500.0)
    assert grid["gps_activity_count"] == 1


def test_corrupt_polyline_does_not_break_the_aggregate():
    # One bad activity must not fail the whole response.
    grid = build_heatmap(["_p~iF~ps|U_ulL", _track_polyline(range(600, 1200, 10))], HOME, 500.0)
    assert grid["gps_activity_count"] == 1
    assert grid["cells"]


def test_route_never_leaving_the_radius_contributes_nothing():
    grid = build_heatmap([_track_polyline(range(0, 400, 10))], HOME, 500.0)
    assert grid == {"cells": [], "bounds": None, "max_count": 0, "gps_activity_count": 0}


def test_cells_are_unique_and_deterministically_ordered():
    grid = build_heatmap([_track_polyline(range(600, 3000, 7))] * 3, HOME, 500.0)
    coords = [(c[0], c[1]) for c in grid["cells"]]
    assert len(coords) == len(set(coords))
    assert coords == sorted(coords)


# --- endpoint contract ------------------------------------------------------

HOME_TRACK_POLYLINE = _track_polyline(range(0, 3000, 10))


def _activity(activity_id=1, polyline=HOME_TRACK_POLYLINE, distance=9399.8):
    from apps.strava.models import StravaActivity

    return StravaActivity(
        id=activity_id,
        name="Morning Run",
        type="Run",
        distance=distance,
        moving_time=3474,
        elapsed_time=3600,
        total_elevation_gain=131.0,
        start_date=datetime(2026, 7, 24, 14, 4, 37, tzinfo=UTC),
        start_date_local=datetime(2026, 7, 24, 16, 4, 37),
        summary_polyline=polyline,
    )


def _fake_db(rows, last_synced="2026-07-24T20:00:00", has_any=True):
    """A session whose aggregate and polyline queries both answer from `rows`."""
    query = MagicMock()
    query.filter.return_value = query
    query.with_entities.return_value.one.return_value = (
        len(rows),
        sum(r.distance for r in rows),
        last_synced,
    )
    query.with_entities.return_value.all.return_value = [(r.summary_polyline,) for r in rows]
    query.first.return_value = object() if has_any else None

    db = MagicMock()
    db.query.return_value = query
    return db


@pytest.fixture
def client(monkeypatch):
    import apps.strava.main as main

    monkeypatch.setattr(settings, "strava_home_lat", HOME[0])
    monkeypatch.setattr(settings, "strava_home_lng", HOME[1])
    monkeypatch.setattr(settings, "strava_privacy_radius_m", 500.0)
    main._HEATMAP_CACHE.clear()  # a process-wide cache would leak between tests
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _use_db(db):
    app.dependency_overrides[get_db] = lambda: db


def test_response_shape_is_stable(client):
    _use_db(_fake_db([_activity()]))
    r = client.get("/strava/heatmap?activity_type=Run")

    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "cell_size_m",
        "bounds",
        "max_count",
        "activity_count",
        "total_distance_m",
        "cells",
    }
    assert body["cell_size_m"] == HEATMAP_CELL_SIZE_M
    assert body["activity_count"] == 1
    assert body["total_distance_m"] == 9400
    assert len(body["bounds"]) == 4

    # Triples, not objects.
    lng, lat, count = body["cells"][0]
    assert isinstance(count, int)
    assert round(lng, CELL_COORD_PRECISION) == lng
    assert round(lat, CELL_COORD_PRECISION) == lat


def test_response_never_leaks_home_coordinate_radius_or_raw_track(client):
    _use_db(_fake_db([_activity()]))
    raw = client.get("/strava/heatmap").text

    assert "59.9139" not in raw
    assert "10.7522" not in raw
    assert "radius" not in raw.lower()
    assert HOME_TRACK_POLYLINE not in raw


def test_response_carries_no_link_back_to_individual_activities(client):
    _use_db(_fake_db([_activity(activity_id=19446762736)]))
    raw = client.get("/strava/heatmap").text

    assert "19446762736" not in raw          # no activity IDs
    assert "start_date" not in raw           # no timestamps
    assert "2026-07-24" not in raw


def test_cells_are_clipped_around_home(client):
    _use_db(_fake_db([_activity()]))
    for lng, lat, _count in client.get("/strava/heatmap").json()["cells"]:
        assert _metres_from_home(lat, lng) > 500.0


def test_wider_radius_clips_more(client, monkeypatch):
    import apps.strava.main as main

    _use_db(_fake_db([_activity()]))
    narrow = client.get("/strava/heatmap").json()["cells"]

    monkeypatch.setattr(settings, "strava_privacy_radius_m", 1500.0)
    main._HEATMAP_CACHE.clear()
    wide = client.get("/strava/heatmap").json()["cells"]

    assert len(wide) < len(narrow)
    for lng, lat, _count in wide:
        assert _metres_from_home(lat, lng) > 1500.0


def test_refuses_to_serve_when_home_is_unconfigured(client, monkeypatch):
    # The fail-closed case: no config must mean no data, not unclipped data.
    monkeypatch.setattr(settings, "strava_home_lat", None)
    _use_db(_fake_db([_activity()]))
    r = client.get("/strava/heatmap")
    assert r.status_code == 503
    assert "cells" not in r.json()


def test_no_matching_activities_is_200_but_unsynced_backend_is_503(client):
    # "No rides logged" and "Strava never synced" must be distinguishable.
    _use_db(_fake_db([], has_any=True))
    r = client.get("/strava/heatmap?activity_type=Ride")
    assert r.status_code == 200
    assert r.json()["cells"] == [] and r.json()["bounds"] is None

    _use_db(_fake_db([], has_any=False))
    assert client.get("/strava/heatmap").status_code == 503


def test_activities_without_gps_still_count_in_the_summary(client):
    # A treadmill run has no track but did happen, and its distance is real.
    _use_db(_fake_db([_activity(polyline=None, distance=5000.0)]))
    body = client.get("/strava/heatmap").json()
    assert body["activity_count"] == 1
    assert body["total_distance_m"] == 5000
    assert body["cells"] == []


# --- caching ----------------------------------------------------------------


def test_etag_revalidation_returns_304(client):
    _use_db(_fake_db([_activity()]))
    first = client.get("/strava/heatmap")
    etag = first.headers["etag"]

    cache_control = first.headers["cache-control"]
    assert cache_control.startswith("public")
    # The aggregate only moves when a new activity is logged.
    assert "max-age=3600" in cache_control
    assert "stale-while-revalidate" in cache_control

    second = client.get("/strava/heatmap", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.headers["etag"] == etag
    assert not second.content


def test_etag_is_weak_and_matches_when_echoed_verbatim(client):
    # Regression guard: the served tag is W/-prefixed, so the If-None-Match
    # comparison has to normalise both sides. Comparing a prefixed tag against
    # stripped candidates silently never matches and 304 stops happening.
    _use_db(_fake_db([_activity()]))
    etag = client.get("/strava/heatmap").headers["etag"]
    assert etag.startswith('W/"')

    for header in (etag, _strip_weak(etag), f'"nope", {etag}', "*"):
        r = client.get("/strava/heatmap", headers={"If-None-Match": header})
        assert r.status_code == 304, f"no 304 for If-None-Match: {header}"


def test_etag_changes_when_privacy_config_changes(client, monkeypatch):
    _use_db(_fake_db([_activity()]))
    before = client.get("/strava/heatmap").headers["etag"]

    monkeypatch.setattr(settings, "strava_privacy_radius_m", 1500.0)
    assert client.get("/strava/heatmap").headers["etag"] != before


def test_etag_changes_when_a_new_activity_is_synced(client):
    _use_db(_fake_db([_activity()], last_synced="2026-07-24T20:00:00"))
    before = client.get("/strava/heatmap").headers["etag"]

    _use_db(_fake_db([_activity(), _activity(activity_id=2)], last_synced="2026-07-25T09:00:00"))
    assert client.get("/strava/heatmap").headers["etag"] != before


def test_etag_distinguishes_activity_types(client):
    _use_db(_fake_db([_activity()]))
    tags = {
        client.get(f"/strava/heatmap{qs}").headers["etag"]
        for qs in ("", "?activity_type=Run", "?activity_type=Ride")
    }
    assert len(tags) == 3


def test_etag_does_not_expose_the_home_coordinate(client):
    # The tag commits to the home coordinate so config changes bust caches, but
    # coordinates are low-entropy: an unkeyed digest could be brute-forced back
    # out of a public header. It is HMACed with a server secret instead.
    import hashlib

    _use_db(_fake_db([_activity()]))
    tag = client.get("/strava/heatmap").headers["etag"]
    guess = hashlib.sha256(f"{HOME[0]}|{HOME[1]}|500.0".encode()).hexdigest()[:32]
    assert guess not in tag


def test_repeat_request_is_served_from_cache_without_reaggregating(client):
    db = _fake_db([_activity()])
    _use_db(db)

    first = client.get("/strava/heatmap").json()
    calls_after_first = db.query.return_value.with_entities.return_value.all.call_count

    second = client.get("/strava/heatmap").json()
    assert second == first
    # The polyline fetch (and the aggregation behind it) did not run again.
    assert db.query.return_value.with_entities.return_value.all.call_count == calls_after_first


def test_large_response_is_compressed(client):
    # Uncompressed a full heat grid is hundreds of KB; the frontend has a 5 s
    # budget and the reverse proxy's compression config lives outside this repo.
    tracks = [
        _activity(activity_id=i, polyline=_track_polyline(range(600, 12000, 6), east_m=i * 40))
        for i in range(40)
    ]
    _use_db(_fake_db(tracks))

    r = client.get("/strava/heatmap", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"
    decoded = r.content
    assert len(decoded) > 100_000
    assert len(gzip.compress(decoded)) < len(decoded) / 2


# --- separation from the lightweight endpoint -------------------------------


def test_cors_allows_the_public_site(client):
    _use_db(_fake_db([_activity()]))
    r = client.get("/strava/heatmap", headers={"Origin": "https://vuhnger.dev"})
    assert r.headers.get("access-control-allow-origin") == "https://vuhnger.dev"


def test_lightweight_activities_endpoint_stays_free_of_geometry(client):
    # The stat cards poll /strava/activities; summary_polyline is unclipped and
    # must never appear there.
    assert "summary_polyline" not in _activity().to_dict()
