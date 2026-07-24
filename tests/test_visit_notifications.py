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


def _post(ip: str, ua: str = "Mozilla/5.0"):
    return TestClient(site.app).post(
        "/site/visit",
        json={"path": "/projects", "referrer": "google.com"},
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
