"""Notifier abstraction + the /site/visit beacon logic."""

from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

import apps.shared.notifications as notif
import apps.site.main as site
from apps.shared.notifications import (
    MultiNotifier,
    NtfyNotifier,
    NullNotifier,
    build_notifier,
)

# --- notifier abstraction --------------------------------------------------

def test_ntfy_notifier_posts_message_title_tags(monkeypatch):
    captured = {}

    def fake_post(url, *, content, headers, timeout):
        captured.update(url=url, content=content, headers=headers)

    monkeypatch.setattr(notif.httpx, "post", fake_post)
    NtfyNotifier("https://ntfy.sh/topic").send("hello", title="T", tags=["wave", "eyes"])

    assert captured["url"] == "https://ntfy.sh/topic"
    assert captured["content"] == b"hello"
    assert captured["headers"]["Title"] == "T"
    assert captured["headers"]["Tags"] == "wave,eyes"


def test_multi_notifier_fans_out_and_survives_a_failure():
    delivered = []

    class Good:
        def send(self, m, *, title=None, tags=None):
            delivered.append(m)

    class Bad:
        def send(self, m, *, title=None, tags=None):
            raise RuntimeError("sink down")

    MultiNotifier([Bad(), Good()]).send("x")  # Bad raising must not stop Good
    assert delivered == ["x"]


def test_build_notifier_picks_provider_from_config(monkeypatch):
    monkeypatch.setattr(notif.settings, "ntfy_url", None)
    assert isinstance(build_notifier(), NullNotifier)
    monkeypatch.setattr(notif.settings, "ntfy_url", "https://ntfy.sh/t")
    assert isinstance(build_notifier(), NtfyNotifier)


# --- /site/visit beacon ----------------------------------------------------

@pytest.fixture
def notifier_mock(monkeypatch):
    site._last_notified.clear()
    monkeypatch.setattr(site, "_geo", lambda ip: "")  # no network
    mock = MagicMock()
    monkeypatch.setattr(site, "notifier", mock)
    return mock


def _post(ip: str, ua: str = "Mozilla/5.0", referrer: str = "google.com", path: str = "/projects"):
    return TestClient(site.app).post(
        "/site/visit",
        json={"path": path, "referrer": referrer},
        headers={"x-forwarded-for": ip, "user-agent": ua},
    )


def test_real_visit_triggers_one_notification(notifier_mock):
    assert _post("9.9.9.9").status_code == 200
    assert notifier_mock.send.call_count == 1


def test_bots_are_ignored(notifier_mock):
    _post("9.9.9.8", ua="Googlebot/2.1 (+http://www.google.com/bot.html)")
    assert notifier_mock.send.call_count == 0


def test_repeat_visit_is_throttled(notifier_mock):
    _post("9.9.9.7")
    _post("9.9.9.7")  # same IP within the window
    assert notifier_mock.send.call_count == 1


def test_excluded_ip_is_ignored(notifier_mock, monkeypatch):
    monkeypatch.setattr(site.settings, "visit_notify_exclude_ips", "9.9.9.6")
    _post("9.9.9.6")
    assert notifier_mock.send.call_count == 0


# --- traffic source --------------------------------------------------------

@pytest.mark.parametrize(
    ("referrer", "path", "expected"),
    [
        ("https://news.ycombinator.com/item?id=1", "/", "news.ycombinator.com"),
        (None, "/?utm_source=linkedin", "linkedin (utm)"),
        (None, "/?ref=cv", "cv (utm)"),
        ("https://t.co/x", "/?utm_source=twitter", "t.co · twitter"),
        (None, "/projects", "direct / unknown"),  # never silent
        ("", None, "direct / unknown"),
    ],
)
def test_source_is_always_reported(referrer, path, expected):
    assert site._source(referrer, path) == expected


def test_notification_body_always_carries_a_source(notifier_mock):
    _post("9.9.9.5", referrer="", path="/")  # browser sent no referrer at all
    assert "↩︎ direct / unknown" in notifier_mock.send.call_args.args[0]


# --- abuse resistance ------------------------------------------------------

def test_oversized_fields_are_rejected_before_reaching_the_notifier(notifier_mock):
    # Unbounded input here meant one request could fabricate a multi-megabyte push.
    resp = TestClient(site.app).post(
        "/site/visit",
        json={"path": "/" + "a" * 5000, "referrer": "b" * 5000},
        headers={"x-forwarded-for": "9.9.9.4", "user-agent": "Mozilla/5.0"},
    )
    assert resp.status_code == 422
    assert notifier_mock.send.call_count == 0


def test_schemeless_referrer_is_truncated_in_the_message():
    assert len(site._source("x" * 250, "/")) == site._MAX_SOURCE_LEN


def test_throttle_map_stays_bounded_under_distinct_ips(monkeypatch):
    # Every entry stays fresh under a burst of new IPs, so expiry alone can't
    # bound the map — it has to evict the oldest too.
    site._last_notified.clear()
    monkeypatch.setattr(site, "_MAX_TRACKED_IPS", 50)
    for i in range(500):
        site._throttle_ok(f"198.51.100.{i}")
    assert len(site._last_notified) <= 50


def test_geo_skips_addresses_that_cannot_resolve(monkeypatch):
    def explode(*a, **kw):  # any outbound call here is a bug
        raise AssertionError("should not perform a lookup")

    monkeypatch.setattr(site.httpx, "get", explode)
    assert site._geo("10.0.0.5") == ""      # private
    assert site._geo("127.0.0.1") == ""     # loopback
    assert site._geo("not-an-ip") == ""     # malformed
