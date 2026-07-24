"""Unit tests for the security-critical shared modules.

These had no coverage despite being the most sensitive code: token encryption
at rest and the HMAC-signed OAuth CSRF state.
"""

import apps.shared.oauth_state as st
from apps.shared.encryption import decrypt_token, encrypt_token


# --- encryption ------------------------------------------------------------

def test_encrypt_decrypt_round_trip():
    token = "strava-access-token-abc123"
    ciphertext = encrypt_token(token)
    assert ciphertext != token  # actually encrypted
    assert decrypt_token(ciphertext) == token


def test_encrypt_is_nondeterministic():
    # Fernet embeds a random IV/timestamp, so the same plaintext encrypts
    # differently each time — both still decrypt back.
    a, b = encrypt_token("x"), encrypt_token("x")
    assert a != b
    assert decrypt_token(a) == decrypt_token(b) == "x"


def test_empty_string_passthrough():
    assert encrypt_token("") == ""
    assert decrypt_token("") == ""


def test_tampered_ciphertext_rejected():
    from cryptography.fernet import InvalidToken
    import pytest

    ciphertext = encrypt_token("secret")
    tampered = ciphertext[:-4] + ("AAAA" if ciphertext[-4:] != "AAAA" else "BBBB")
    with pytest.raises(InvalidToken):
        decrypt_token(tampered)


# --- oauth_state -----------------------------------------------------------

def test_state_round_trip():
    state = st.generate_state()
    assert isinstance(state, str) and state
    assert st.validate_state(state) is True


def test_garbage_state_rejected():
    assert st.validate_state("not-a-valid-state") is False


def test_tampered_state_rejected():
    state = st.generate_state()
    tampered = state[:-2] + ("aa" if state[-2:] != "aa" else "bb")
    assert st.validate_state(tampered) is False


def test_expired_state_rejected(monkeypatch):
    state = st.generate_state()  # signed with the current timestamp
    # Jump the clock past the expiry window; the signature is still valid but
    # the state must be rejected as stale. Capture the real time.time first so
    # the patched version doesn't call itself.
    real_time = st.time.time
    monkeypatch.setattr(st.time, "time", lambda: real_time() + st.STATE_EXPIRY + 10)
    assert st.validate_state(state) is False
