"""Site service — a lightweight beacon the frontend pings on page load.

When a *new* visitor arrives it pushes a notification via the pluggable notifier
(ntfy today, more later). Historical analytics live in Umami; this is only the
real-time "someone's here" ping. No DB — throttling is in-memory, which is fine
for this single-worker deployment.
"""

import logging
import time

import httpx
from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel

from apps.shared.app_factory import create_app, include_versioned
from apps.shared.config import settings
from apps.shared.notifications import notifier

logger = logging.getLogger(__name__)

app = create_app(
    title="Site Service",
    url_prefix="site",
    description="Visitor beacon that pushes a notification on a new visit",
)
router = APIRouter(prefix="/site")

# In-memory throttle: client IP -> epoch seconds of last notification.
_last_notified: dict[str, float] = {}

# Substrings that mark a request as a bot/crawler/monitor we don't want pinged for.
_BOT_MARKERS = (
    "bot", "crawl", "spider", "slurp", "bingpreview", "facebookexternalhit",
    "headless", "monitor", "uptime", "curl", "wget", "python-httpx", "go-http",
)


class VisitIn(BaseModel):
    path: str | None = None
    referrer: str | None = None


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


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
    if len(_last_notified) > 10_000:  # opportunistic cleanup of stale entries
        cutoff = now - window
        for stale in [k for k, v in _last_notified.items() if v < cutoff]:
            _last_notified.pop(stale, None)
    return True


def _geo(ip: str) -> str:
    """Best-effort 'City, Country' from IP. Never raises; '' on any failure."""
    try:
        resp = httpx.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "country,city"},
            timeout=3.0,
        )
        data = resp.json()
        return ", ".join(p for p in (data.get("city"), data.get("country")) if p)
    except Exception:
        return ""


def _notify_visit(ip: str, user_agent: str, path: str | None, referrer: str | None) -> None:
    where = _geo(ip)
    device = "mobile" if "mobi" in user_agent.lower() else "desktop"
    lines = [f"👤 New visit: {path or '/'}"]
    if where:
        lines.append(f"📍 {where}")
    if referrer:
        lines.append(f"↩︎ from {referrer}")
    lines.append(f"🖥 {device}")
    notifier.send("\n".join(lines), title="vuhnger.dev", tags=["wave"])


@router.get("/health")
def health():
    return {"status": "ok", "service": "site"}


@router.post("/visit")
def visit(payload: VisitIn, request: Request, background_tasks: BackgroundTasks):
    """Fire-and-forget beacon: returns 200 immediately; notification runs in the
    background, and only for a genuine, non-throttled, non-excluded visitor."""
    ip = _client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    if (
        not _looks_like_bot(user_agent)
        and ip not in settings.excluded_visit_ips
        and _throttle_ok(ip)
    ):
        background_tasks.add_task(_notify_visit, ip, user_agent, payload.path, payload.referrer)
    return {"ok": True}


include_versioned(app, router)
