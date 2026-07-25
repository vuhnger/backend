"""Every Strava call is bounded by a timeout.

stravalib calls `requests` without a timeout and `requests` has no default, so a
stalled Strava endpoint would block the calling thread forever — permanently
consuming one of uvicorn's threadpool workers per hung call.
"""

import inspect

import apps.strava.client as strava_api
import apps.strava.main as strava_main
from apps.strava.client_factory import STRAVA_TIMEOUT, strava_client


def test_session_injects_a_default_timeout(monkeypatch):
    seen = {}

    def fake_request(self, *args, **kwargs):
        seen.update(kwargs)
        return None

    import requests

    monkeypatch.setattr(requests.Session, "request", fake_request)
    client = strava_client("token")
    client.protocol.rsession.get("https://example.invalid")

    assert seen["timeout"] == STRAVA_TIMEOUT


def test_an_explicit_timeout_still_wins(monkeypatch):
    seen = {}

    def fake_request(self, *args, **kwargs):
        seen.update(kwargs)
        return None

    import requests

    monkeypatch.setattr(requests.Session, "request", fake_request)
    strava_client().protocol.rsession.get("https://example.invalid", timeout=1.0)

    assert seen["timeout"] == 1.0


def test_no_module_builds_a_bare_stravalib_client():
    # A raw `Client(...)` anywhere would silently reintroduce the unbounded call.
    for module in (strava_api, strava_main):
        source = inspect.getsource(module)
        assert "Client(" not in source, f"{module.__name__} bypasses strava_client()"
