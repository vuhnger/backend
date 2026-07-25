"""Site service — a lightweight beacon the frontend pings on page load.

When a *new* visitor arrives it pushes a notification via the pluggable notifier
(ntfy today, more later). Historical analytics live in Umami; this is only the
real-time "someone's here" ping. No DB — throttling is in-memory, which is fine
for this single-worker deployment.
"""

import ipaddress
import logging
import time
from collections import OrderedDict
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel, Field

from apps.shared.app_factory import create_app, include_versioned
from apps.shared.config import settings
from apps.shared.net import client_ip
from apps.shared.notifications import notifier

logger = logging.getLogger(__name__)

app = create_app(
    title="Site Service",
    url_prefix="site",
    description="Visitor beacon that pushes a notification on a new visit",
)
router = APIRouter(prefix="/site")

# In-memory throttle: client IP -> epoch seconds of last notification. Ordered so
# the oldest entry can be evicted once the map is full — expiry alone isn't enough,
# because a burst of distinct IPs produces entries that are all still fresh.
_MAX_TRACKED_IPS = 10_000
_last_notified: OrderedDict[str, float] = OrderedDict()

# Longest values we'll echo into a push notification. The payload is public and
# unauthenticated, so without a cap a single request can fabricate a multi-megabyte
# notification body.
_MAX_FIELD_LEN = 300
_MAX_SOURCE_LEN = 100

# Substrings that mark a request as a bot/crawler/monitor we don't want pinged for.
_BOT_MARKERS = (
    "bot", "crawl", "spider", "slurp", "bingpreview", "facebookexternalhit",
    "headless", "monitor", "uptime", "curl", "wget", "python-httpx", "go-http",
)


# Query params that identify a traffic source. They survive where document.referrer
# doesn't, so they're the fallback when the browser sends no referrer.
_CAMPAIGN_PARAMS = ("utm_source", "ref", "source")


class VisitIn(BaseModel):
    # `path` may include the query string (e.g. "/?utm_source=linkedin") — send
    # `location.pathname + location.search` from the frontend to get campaign data.
    # Both fields are length-capped: pydantic rejects anything longer with a 422,
    # so oversized values never reach the notifier.
    path: str | None = Field(default=None, max_length=_MAX_FIELD_LEN)
    referrer: str | None = Field(default=None, max_length=_MAX_FIELD_LEN)


def _looks_like_bot(user_agent: str) -> bool:
    ua = user_agent.lower()
    return not ua or any(marker in ua for marker in _BOT_MARKERS)


def _throttle_ok(ip: str) -> bool:
    """True if this IP hasn't been notified within the throttle window (and records it)."""
    now = time.time()
    window = settings.visit_notify_throttle_seconds
    last = _last_notified.get(ip)
    if last is not None and now - last < window:
        return False
    _last_notified[ip] = now
    _last_notified.move_to_end(ip)

    # Drop expired entries first, then — if the map is still full — the oldest
    # ones. The expiry sweep alone leaves the map unbounded, because entries only
    # become droppable after a full window has passed.
    cutoff = now - window
    for stale in [k for k, v in _last_notified.items() if v < cutoff]:
        del _last_notified[stale]
    while len(_last_notified) > _MAX_TRACKED_IPS:
        _last_notified.popitem(last=False)
    return True


def _geo(ip: str) -> str:
    """Best-effort 'City, Country' from IP. Never raises; '' on any failure.

    The address is validated before it reaches the URL so a malformed value can't
    shape the outbound request, and private/loopback addresses are skipped — a
    lookup for them is guaranteed useless. Note the provider's free tier is
    plaintext HTTP, so visitor IPs travel in the clear; ``GEO_LOOKUP_URL`` exists
    so that can be pointed at an HTTPS provider without a code change.
    """
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    if parsed.is_private or parsed.is_loopback or parsed.is_reserved:
        return ""

    try:
        resp = httpx.get(
            settings.geo_lookup_url.format(ip=parsed),
            params={"fields": "country,city"},
            timeout=3.0,
        )
        data = resp.json()
        located = ", ".join(p for p in (data.get("city"), data.get("country")) if p)
        return located[:_MAX_SOURCE_LEN]
    except Exception:
        return ""


def _campaign(path: str | None) -> str:
    """The utm_source/ref value from the visited URL's query string, or ''."""
    if not path or "?" not in path:
        return ""
    params = parse_qs(urlsplit(path).query)
    for key in _CAMPAIGN_PARAMS:
        values = params.get(key)
        if values and values[0]:
            return values[0][:60]
    return ""


def _source(referrer: str | None, path: str | None) -> str:
    """Where the visitor came from — always a non-empty, human-readable string.

    ``document.referrer`` is empty for direct visits, bookmarks, and any client
    sending ``Referrer-Policy: no-referrer`` (most in-app browsers strip it), so we
    fall back to campaign params and otherwise say "unknown" explicitly. Staying
    silent would make "no referrer" indistinguishable from "beacon didn't send it".
    """
    campaign = _campaign(path)
    if referrer:
        # A referrer without a scheme has no netloc, so the raw value is the
        # fallback — cap it, since it's attacker-supplied and ends up in a push.
        host = (urlsplit(referrer).netloc or referrer)[:_MAX_SOURCE_LEN]
        return f"{host} · {campaign}" if campaign else host
    if campaign:
        return f"{campaign} (utm)"
    return "direct / unknown"


def _notify_visit(ip: str, user_agent: str, path: str | None, referrer: str | None) -> None:
    where = _geo(ip)
    device = "mobile" if "mobi" in user_agent.lower() else "desktop"
    source = _source(referrer, path)
    # Logged without the IP on purpose: geo is enough to recognise a visit later,
    # and the raw address is personal data we have no reason to retain.
    logger.info(
        "visit notified: path=%s source=%s geo=%s device=%s",
        path or "/", source, where or "?", device,
    )
    lines = [f"👤 New visit: {path or '/'}"]
    if where:
        lines.append(f"📍 {where}")
    lines.append(f"↩︎ {source}")
    lines.append(f"🖥 {device}")
    notifier.send("\n".join(lines), title="vuhnger.dev", tags=["wave"])


@router.get("/health")
def health():
    return {"status": "ok", "service": "site"}


@router.post("/visit")
def visit(payload: VisitIn, request: Request, background_tasks: BackgroundTasks):
    """Fire-and-forget beacon: returns 200 immediately; notification runs in the
    background, and only for a genuine, non-throttled, non-excluded visitor."""
    ip = client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    if (
        not _looks_like_bot(user_agent)
        and ip not in settings.excluded_visit_ips
        and _throttle_ok(ip)
    ):
        background_tasks.add_task(_notify_visit, ip, user_agent, payload.path, payload.referrer)
    return {"ok": True}


include_versioned(app, router)
