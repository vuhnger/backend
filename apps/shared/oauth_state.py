"""
OAuth State Management

Provides secure per-request OAuth state generation and validation
to prevent CSRF attacks in OAuth 2.0 flows.
"""
import os
import time
import hmac
import hashlib
import secrets
import base64
from typing import Optional


# State secret for HMAC signing (must be set in production)
STATE_SECRET = os.getenv("STATE_SECRET")

# State expiry time in seconds (10 minutes)
STATE_EXPIRY = 600


def generate_state() -> str:
    """
    Generate a secure, time-bound OAuth state parameter.

    The state includes:
    - Current timestamp (for expiry validation)
    - Random nonce (for uniqueness)
    - HMAC signature (for authenticity)

    Returns:
        Base64-encoded state string

    Raises:
        RuntimeError: If STATE_SECRET is not configured
    """
    if not STATE_SECRET:
        raise RuntimeError(
            "STATE_SECRET environment variable must be set for OAuth security. "
            "Generate one with: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )

    # Create payload with timestamp and nonce
    timestamp = int(time.time())
    nonce = secrets.token_urlsafe(16)
    payload = f"{timestamp}:{nonce}"

    # Sign the payload with HMAC-SHA256
    # Use 32 hex characters (128 bits) per OWASP recommendation for HMAC signatures
    signature = hmac.new(
        STATE_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()[:32]

    # Combine and encode
    full_state = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(full_state.encode()).decode()


def validate_state(state: str) -> bool:
    """
    Validate an OAuth state parameter.

    Checks:
    1. State can be decoded
    2. Signature is valid (prevents tampering)
    3. State is not expired (prevents replay attacks)

    Args:
        state: The state parameter received from OAuth callback

    Returns:
        True if state is valid, False otherwise

    Raises:
        RuntimeError: If STATE_SECRET environment variable is not configured
    """
    if not STATE_SECRET:
        raise RuntimeError("STATE_SECRET environment variable must be set")

    try:
        # Decode base64
        decoded = base64.urlsafe_b64decode(state.encode()).decode()

        # Parse components
        parts = decoded.rsplit(":", 2)
        if len(parts) != 3:
            return False

        timestamp_str, nonce, received_signature = parts
        timestamp = int(timestamp_str)

        # Reconstruct payload and verify signature
        # Use 32 hex characters (128 bits) per OWASP recommendation for HMAC signatures
        payload = f"{timestamp_str}:{nonce}"
        expected_signature = hmac.new(
            STATE_SECRET.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()[:32]

        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(received_signature, expected_signature):
            return False

        # Check expiry
        current_time = int(time.time())
        if timestamp + STATE_EXPIRY < current_time:
            return False

        return True

    except (ValueError, UnicodeDecodeError, base64.binascii.Error):
        # Invalid format
        return False


def get_state_expiry_seconds() -> int:
    """Get the state expiry time in seconds."""
    return STATE_EXPIRY
