"""Token refresh: response decoding, expiry, and isolation from the caller.

Each test here corresponds to a defect that was live in both provider apps.
"""

import time
from types import SimpleNamespace

import httpx
import pytest

from apps.shared import oauth_tokens
from apps.shared.oauth_tokens import (
    TokenSet,
    needs_refresh,
    parse_expiry,
    parse_token_response,
    refresh_token_locked,
)

# --- response decoding -----------------------------------------------------

def _response(text: str, content_type: str) -> httpx.Response:
    return httpx.Response(200, text=text, headers={"content-type": content_type})


def test_json_response_is_decoded():
    resp = _response('{"access_token":"a"}', "application/json")
    assert parse_token_response(resp) == {"access_token": "a"}


def test_form_encoded_response_is_decoded():
    # WakaTime answers form-encoded. The refresh path called .json() directly, so
    # it raised on every attempt and the integration died ~1h after each login.
    resp = _response("access_token=a&refresh_token=b", "application/x-www-form-urlencoded")
    assert parse_token_response(resp) == {"access_token": "a", "refresh_token": "b"}


# --- expiry ----------------------------------------------------------------

def test_expires_in_is_relative_to_now():
    assert parse_expiry({"expires_in": "7200"}) == pytest.approx(time.time() + 7200, abs=2)


def test_numeric_expires_at_is_used_verbatim():
    # The old code read this field, threw the value away, and stored now+3600.
    assert parse_expiry({"expires_at": 1893456000}) == 1893456000


def test_iso_expires_at_is_parsed():
    assert parse_expiry({"expires_at": "2030-01-01T00:00:00Z"}) == 1893456000


def test_unparseable_expiry_falls_back_conservatively(caplog):
    got = parse_expiry({"token_type": "Bearer"})
    assert got == pytest.approx(time.time() + 3600, abs=2)
    assert "no parseable expiry" in caplog.text  # must not fail silently


# --- locking / isolation ---------------------------------------------------

class _FakeSession:
    """Records the calls refresh_token_locked makes on its own session."""

    def __init__(self, auth, log):
        self._auth = auth
        self.log = log
        self._for_update = False

    def query(self, model):
        return self

    def filter(self, *args):
        return self

    def with_for_update(self):
        self._for_update = True
        self.log.append("locked")
        return self

    def first(self):
        return self._auth

    def commit(self):
        self.log.append("commit")

    def rollback(self):
        self.log.append("rollback")

    def close(self):
        self.log.append("close")


@pytest.fixture
def session_log(monkeypatch):
    log: list[str] = []
    holder = {}

    def factory():
        session = _FakeSession(holder.get("auth"), log)
        return session

    monkeypatch.setattr(oauth_tokens, "SessionLocal", factory)
    return log, holder


def _auth(expires_at):
    return SimpleNamespace(
        expires_at=expires_at, access_token="old", refresh_token="old-refresh"
    )


def test_refresh_takes_a_row_lock_and_commits_on_its_own_session(session_log):
    log, holder = session_log
    holder["auth"] = _auth(int(time.time()))  # expired
    exchanged = TokenSet("new", "new-refresh", 9999999999)

    refresh_token_locked(type("M", (), {"id": 1, "__tablename__": "m"}), lambda _: exchanged, 300)

    # The lock is what stops two callers from both spending the same refresh
    # token — providers rotate them, so the loser's token is dead for good.
    assert log == ["locked", "commit", "close"]
    assert holder["auth"].access_token == "new"


def test_a_refresh_already_done_by_another_caller_is_skipped(session_log):
    log, holder = session_log
    holder["auth"] = _auth(int(time.time()) + 100_000)  # someone else just refreshed

    def exchange(_):
        raise AssertionError("must not spend a refresh token that isn't needed")

    refresh_token_locked(type("M", (), {"id": 1, "__tablename__": "m"}), exchange, 300)
    assert log == ["locked", "close"]  # no commit: nothing to do


def test_a_failed_exchange_rolls_back_only_its_own_session(session_log):
    log, holder = session_log
    holder["auth"] = _auth(int(time.time()))

    def exchange(_):
        raise RuntimeError("provider down")

    with pytest.raises(RuntimeError):
        refresh_token_locked(type("M", (), {"id": 1, "__tablename__": "m"}), exchange, 300)

    # Previously this ran on the caller's session, so the rollback threw away
    # whatever bulk activity upserts that session had pending.
    assert log == ["locked", "rollback", "close"]


def test_needs_refresh_respects_the_buffer():
    assert needs_refresh(int(time.time()) + 100, buffer_seconds=300)
    assert not needs_refresh(int(time.time()) + 1000, buffer_seconds=300)
