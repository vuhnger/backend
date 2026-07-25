"""Shared OAuth token refresh.

Both providers had their own near-identical copy of this, and both copies shared
two defects:

**The refresh committed on the caller's session.** ``get_valid_token(db)`` is
called from the middle of a sync task that has already queued bulk activity
upserts on the same session. A refresh triggering there committed that
half-finished sync — and if the refresh then failed, its ``rollback()`` threw the
pending upserts away. The refresh now runs in its own short-lived session, so it
can never commit or discard the caller's work.

**Read-check-refresh had no lock.** Two callers (the cron sync and a manual
/refresh-data, say) could both see an expiring token and both POST the same
refresh token. Providers rotate refresh tokens, so the second response
invalidates the first and the stored token can end up permanently dead —
requiring a manual re-authorization. The refresh now takes a row lock and
re-checks after acquiring it, so the second caller finds the work already done.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs

import httpx

from apps.shared.database import SessionLocal

logger = logging.getLogger(__name__)

# Every outbound call needs a timeout; a hung provider must not pin a worker.
HTTP_TIMEOUT = 10.0

# Used only when a provider's response carries no parseable expiry at all. Short
# and loudly logged: guessing long would hand out a token we believe in but the
# provider has already rejected.
_FALLBACK_EXPIRY_SECONDS = 3600


@dataclass(frozen=True)
class TokenSet:
    """The three fields every refresh has to produce."""

    access_token: str
    refresh_token: str
    expires_at: int


def needs_refresh(expires_at: int, buffer_seconds: int = 300) -> bool:
    """True if the token expires within ``buffer_seconds``."""
    return time.time() >= (expires_at - buffer_seconds)


def parse_token_response(response: httpx.Response) -> dict[str, Any]:
    """Decode a token response as JSON, falling back to form-encoded.

    WakaTime answers ``application/x-www-form-urlencoded`` rather than JSON. The
    OAuth callback handled that; the refresh path did not, and called ``.json()``
    directly — so refresh raised ``ValueError`` on every attempt while the initial
    authorization worked, and the integration died about an hour after each login.
    """
    try:
        return response.json()
    except ValueError:
        return {key: values[0] for key, values in parse_qs(response.text).items() if values}


def parse_expiry(token_data: dict[str, Any]) -> int:
    """Absolute expiry (unix seconds) from a token response.

    Accepts ``expires_in`` (seconds from now), a numeric ``expires_at``, or an
    ISO-8601 ``expires_at``. The previous WakaTime code read ``expires_at``,
    discarded it, and stored ``now + 3600`` regardless — so the stored expiry was
    fiction and the token was refreshed roughly hourly no matter what.
    """
    now = int(time.time())

    if "expires_in" in token_data:
        return now + int(float(token_data["expires_in"]))

    raw = token_data.get("expires_at")
    if raw is not None:
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            pass
        try:
            text = str(raw).replace("Z", "+00:00")
            return int(datetime.fromisoformat(text).timestamp())
        except ValueError:
            pass

    logger.error(
        "token response carried no parseable expiry (keys: %s); assuming %ds",
        sorted(token_data), _FALLBACK_EXPIRY_SECONDS,
    )
    return now + _FALLBACK_EXPIRY_SECONDS


def refresh_token_locked(
    model: type[Any],
    exchange: Callable[[str], TokenSet],
    buffer_seconds: int,
) -> None:
    """Refresh the stored grant under a row lock, in an isolated session.

    Args:
        model: The auth model holding the single-user row (id=1).
        exchange: Given the current refresh token, performs the provider call and
            returns the new ``TokenSet``.
        buffer_seconds: Re-check window; if another caller already refreshed while
            this one waited for the lock, there is nothing left to do.

    Raises:
        ValueError: If no authorization row exists yet.
    """
    session = SessionLocal()
    try:
        auth = session.query(model).filter(model.id == 1).with_for_update().first()
        if auth is None:
            raise ValueError(
                f"No {model.__tablename__} row found. Complete the OAuth flow first."
            )

        # Double-checked under the lock: whoever held it before us may already
        # have done this exact refresh, and reusing a rotated token would fail.
        if not needs_refresh(auth.expires_at, buffer_seconds):
            return

        tokens = exchange(auth.refresh_token)
        auth.access_token = tokens.access_token
        auth.refresh_token = tokens.refresh_token
        auth.expires_at = tokens.expires_at
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
