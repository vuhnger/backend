"""The OAuth callbacks may only be completed by the account that owns them.

Both callbacks are public by necessity — the provider redirects a browser to them
— and the signed state proves only that this server minted it, not who for. So
anyone could authorize with their own account and overwrite the single-user row,
destroying the owner's grant and repointing the public portfolio at their data.
"""

import pytest
from fastapi import HTTPException

from apps.shared.oauth_owner import enforce_owner


class _Auth:
    """Stand-in for StravaAuth/WakaTimeAuth — only the id fields matter here."""

    id = 1

    def __init__(self, athlete_id):
        self.athlete_id = athlete_id


class _Session:
    """Minimal db.query(model).filter(...).first() chain."""

    def __init__(self, existing):
        self._existing = existing

    def query(self, model):
        return self

    def filter(self, *args):
        return self

    def first(self):
        return self._existing


def _enforce(existing, incoming, configured=None):
    enforce_owner(
        db=_Session(existing),
        model=_Auth,
        id_field="athlete_id",
        incoming_id=incoming,
        configured_owner=configured,
        provider="test",
    )


def test_first_authorization_establishes_the_owner():
    _enforce(existing=None, incoming=12345)  # no row yet: must be allowed


def test_the_owner_can_reauthorize():
    _enforce(existing=_Auth(12345), incoming=12345)


def test_a_different_account_is_rejected():
    # The attack: authorize with your own account, overwrite row id=1.
    with pytest.raises(HTTPException) as exc:
        _enforce(existing=_Auth(12345), incoming=99999)
    assert exc.value.status_code == 403


def test_id_type_mismatch_does_not_lock_the_owner_out():
    # Providers return ids as int or str depending on the endpoint used.
    _enforce(existing=_Auth("12345"), incoming=12345)


def test_configured_owner_overrides_the_stored_row():
    # The escape hatch for re-establishing ownership after the row is wiped.
    _enforce(existing=None, incoming=12345, configured="12345")
    with pytest.raises(HTTPException):
        _enforce(existing=None, incoming=99999, configured="12345")
