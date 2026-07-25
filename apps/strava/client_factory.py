"""Build stravalib clients that cannot hang forever.

stravalib issues every request through ``requests`` without passing a timeout
(``protocol.py``: ``requester(url, params=params, json=body)``), and ``requests``
has no default. A Strava endpoint that accepts the connection and then stalls
therefore blocks the calling thread indefinitely — which, for the sync endpoints
here, means one of uvicorn's threadpool workers is gone for good. A handful of
those and the service stops answering anything.

``requests`` exposes the timeout only per-call, so the only place to inject a
default is the session itself. Every ``Client`` in this app must come from
``strava_client()``.
"""

import requests
from stravalib.client import Client

# (connect, read) seconds. Connect is short — Strava either answers or it doesn't.
# Read is generous enough for the heavier activity pages.
STRAVA_TIMEOUT = (5.0, 30.0)


class _TimeoutSession(requests.Session):
    """A session that applies STRAVA_TIMEOUT to any request that omits one."""

    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", STRAVA_TIMEOUT)
        return super().request(*args, **kwargs)


def strava_client(access_token: str | None = None) -> Client:
    """A stravalib client whose every call is bounded by STRAVA_TIMEOUT."""
    return Client(access_token=access_token, requests_session=_TimeoutSession())
