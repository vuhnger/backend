"""Route geometry: encoded polylines -> a privacy-safe, aggregated heat grid.

Strava ships ``SummaryActivity.map.summary_polyline`` in the *list* response, so
the route shapes come for free with the activity sync — no per-activity detail
call, no N+1 against the 100-req/15-min rate limit.

Those tracks are absolute WGS84 and are destined for a public page, so two
things happen before anything is served:

1. ``clip_home_area`` removes everything within a configured radius of home. A
   start point at the door reveals a home address and, with timestamps, when
   nobody is in. Strava's own privacy zones do not necessarily apply to what you
   fetch with your own token, so the clipping happens here.
2. ``build_heatmap`` collapses what's left into counts on a coarse grid. The
   output has no timestamps, no activity IDs, and no ordering — individual runs
   cannot be reconstructed from it, only the aggregate shape of where the
   running happens.

Both take the home coordinate and radius as required arguments rather than
reading config themselves: it keeps them pure and testable, and forces every
caller to make a deliberate decision about where home is.
"""

import logging
import math

logger = logging.getLogger(__name__)

# Google encoded-polyline precision used by Strava.
POLYLINE_PRECISION = 5

# Heat grid resolution. 15 m is about the width of a road, which is the scale at
# which "I run here often" is meaningful — finer just splits one path across
# several cells and multiplies the payload.
HEATMAP_CELL_SIZE_M = 15.0

# Decimal places on the emitted cell coordinates. At 4 places a degree of
# latitude resolves to ~11 m, i.e. finer than the cell itself, so this rounding
# never merges cells that the grid meant to keep apart — and it keeps the JSON
# roughly half the size of full float output.
CELL_COORD_PRECISION = 4

# Metres per degree of latitude (mean value). Accurate to ~0.5% anywhere on
# Earth, far inside the tolerance of both the privacy radius and a 15 m cell;
# longitude is additionally scaled by cos(latitude).
METERS_PER_DEGREE_LAT = 111_320.0

# A varint in this encoding is at most 6 groups of 5 bits. Anything longer is
# malformed input, not a huge number — bail instead of looping.
_MAX_VARINT_SHIFT = 30


def decode_polyline(encoded: str, precision: int = POLYLINE_PRECISION) -> list[tuple[float, float]]:
    """Decode a Google encoded polyline into ``(lat, lng)`` pairs.

    Implemented here rather than pulled in as a dependency: it is ~30 lines of a
    frozen, fully specified format, and this way the input validation is ours.

    Raises:
        ValueError: the string is truncated, contains characters outside the
            encoding's range, or yields coordinates off the globe.
    """
    factor = 10**precision
    length = len(encoded)
    index = 0
    lat = 0
    lng = 0
    coords: list[tuple[float, float]] = []

    while index < length:
        deltas = []
        for _ in range(2):  # latitude delta, then longitude delta
            result = 0
            shift = 0
            while True:
                if index >= length:
                    raise ValueError("truncated polyline: varint ends mid-sequence")
                byte = ord(encoded[index]) - 63
                index += 1
                # The format only uses ASCII 63..126, i.e. 0..0x3F after the
                # offset. Anything higher would silently contribute junk bits
                # and decode into a plausible-looking but fabricated route.
                if not 0 <= byte <= 0x3F:
                    raise ValueError("invalid character in polyline")
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
                if shift > _MAX_VARINT_SHIFT:
                    raise ValueError("malformed polyline: varint too long")
            # Low bit is the sign flag; the value is zigzag-encoded.
            deltas.append(~(result >> 1) if result & 1 else (result >> 1))

        lat += deltas[0]
        lng += deltas[1]
        point = (lat / factor, lng / factor)
        if not (-90.0 <= point[0] <= 90.0 and -180.0 <= point[1] <= 180.0):
            raise ValueError("polyline decodes to coordinates off the globe")
        coords.append(point)

    return coords


def _distance_m(lat: float, lng: float, home: tuple[float, float], lng_scale: float) -> float:
    """Metres from ``home``, using an equirectangular approximation.

    At a few-hundred-metre scale the error versus haversine is centimetres, and
    it avoids a trig call per point. The longitude difference is wrapped into
    [-180, 180) so a home near the antimeridian doesn't read as ~360° away from
    a point just across it — which would keep an in-radius point.
    """
    home_lat, home_lng = home
    dy = (lat - home_lat) * METERS_PER_DEGREE_LAT
    dx = ((lng - home_lng + 180.0) % 360.0 - 180.0) * lng_scale
    return math.hypot(dx, dy)


def clip_home_area(
    points: list[tuple[float, float]],
    home: tuple[float, float],
    radius_m: float,
) -> list[tuple[float, float]]:
    """Drop every point within ``radius_m`` of ``home``.

    Every point inside the radius goes, not just the leading and trailing ones.
    A run that happens to pass the house mid-route would otherwise leak the exact
    address from the middle of the track, which defeats the purpose of clipping
    the ends at all.

    Unlike a route being drawn as a line, the heat grid has no connectivity to
    preserve — the points are about to become unordered cell counts — so the
    surviving points are simply returned as-is. Nothing is interpolated across
    the excluded area, and no line is drawn through it.

    Returns an empty list when the whole route sits inside the radius, e.g. a
    short loop around the block.
    """
    if radius_m <= 0:
        raise ValueError("radius_m must be greater than 0")

    lng_scale = METERS_PER_DEGREE_LAT * math.cos(math.radians(home[0]))
    return [(lat, lng) for lat, lng in points if _distance_m(lat, lng, home, lng_scale) > radius_m]


def grid_steps(cell_size_m: float, reference_lat: float) -> tuple[float, float]:
    """Degree-sized grid steps for roughly square ``cell_size_m`` cells.

    Longitude degrees shrink toward the poles, so the east-west step is scaled by
    cos(latitude) — at 60°N a degree of longitude is half a degree of latitude,
    and skipping this would make every cell twice as wide as it is tall.

    A single reference latitude is used for the whole grid rather than each
    point's own, so the grid stays uniform and a point can't land in two
    different cells depending on rounding order.
    """
    if cell_size_m <= 0:
        raise ValueError("cell_size_m must be greater than 0")
    lat_step = cell_size_m / METERS_PER_DEGREE_LAT
    lng_step = cell_size_m / (METERS_PER_DEGREE_LAT * math.cos(math.radians(reference_lat)))
    return lat_step, lng_step


def track_cells(
    points: list[tuple[float, float]],
    lat_step: float,
    lng_step: float,
) -> set[tuple[float, float]]:
    """Snap a track's points to grid cells, returning the distinct ``(lng, lat)`` centres.

    Deduplicated *within* the track on purpose: a cell is counted once per
    activity, not once per GPS sample. Sampling density varies with pace, so
    counting raw samples would light up the places you run slowest rather than
    the places you run often — and it would encode a lingering signal, which is
    exactly the kind of detail this aggregate is meant to drop.

    Coordinates are rounded to the emitted precision here rather than at
    serialization time, so cells that round together are merged into one entry
    instead of appearing twice with split counts.
    """
    cells = set()
    for lat, lng in points:
        cell_lat = round(round(lat / lat_step) * lat_step, CELL_COORD_PRECISION)
        cell_lng = round(round(lng / lng_step) * lng_step, CELL_COORD_PRECISION)
        cells.add((cell_lng, cell_lat))
    return cells


def build_heatmap(
    polylines: list[str | None],
    home: tuple[float, float],
    radius_m: float,
    cell_size_m: float = HEATMAP_CELL_SIZE_M,
) -> dict:
    """Aggregate encoded polylines into ``{cells, bounds, max_count, gps_activity_count}``.

    ``cells`` is a list of ``[lng, lat, count]`` triples — arrays rather than
    objects, which drops the repeated key names that would otherwise dominate the
    payload — sorted for a deterministic response (which also compresses better,
    since neighbouring cells share coordinate prefixes).

    ``count`` is the number of *activities* that touched the cell.

    ``bounds`` is ``[min_lng, min_lat, max_lng, max_lat]``, or None when nothing
    survived. A polyline that fails to decode is logged and skipped: one corrupt
    activity must not fail the whole aggregate.
    """
    lat_step, lng_step = grid_steps(cell_size_m, home[0])
    lng_scale = METERS_PER_DEGREE_LAT * math.cos(math.radians(home[0]))

    # Clipping removes *points* inside the radius, but snapping then moves each
    # survivor up to half a cell diagonal — so a point legally 501 m out can
    # produce a cell centred at 490 m, publishing a corner of the excluded area.
    # Cells are therefore re-checked against the radius plus the cell's own
    # reach, which guarantees no emitted cell even overlaps the exclusion circle.
    cell_reach_m = cell_size_m * math.sqrt(2) / 2
    min_cell_distance_m = radius_m + cell_reach_m

    counts: dict[tuple[float, float], int] = {}
    gps_activity_count = 0

    for encoded in polylines:
        if not encoded:
            continue  # recorded without GPS (treadmill)
        try:
            coords = decode_polyline(encoded)
        except ValueError as exc:
            logger.warning("Skipping unparseable route polyline: %s", exc)
            continue

        kept = clip_home_area(coords, home, radius_m)
        if not kept:
            continue  # never left the privacy radius

        cells = {
            (lng, lat)
            for lng, lat in track_cells(kept, lat_step, lng_step)
            if _distance_m(lat, lng, home, lng_scale) >= min_cell_distance_m
        }
        if not cells:
            continue

        gps_activity_count += 1
        for cell in cells:
            counts[cell] = counts.get(cell, 0) + 1

    if not counts:
        return {"cells": [], "bounds": None, "max_count": 0, "gps_activity_count": 0}

    cells = [[lng, lat, count] for (lng, lat), count in sorted(counts.items())]
    lngs = [c[0] for c in cells]
    lats = [c[1] for c in cells]

    return {
        "cells": cells,
        "bounds": [min(lngs), min(lats), max(lngs), max(lats)],
        "max_count": max(counts.values()),
        "gps_activity_count": gps_activity_count,
    }
