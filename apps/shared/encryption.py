"""
Token Encryption Utilities

Provides symmetric encryption for OAuth tokens at rest using Fernet (AES-128-CBC).
"""

import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


# Get encryption key from environment
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

# Salt for key derivation (fixed salt is okay for this use case since key is secret)
SALT = b"strava_wakatime_backend_salt_v1"


def _get_fernet() -> Fernet:
    """
    Get Fernet cipher instance.

    Raises:
        RuntimeError: If ENCRYPTION_KEY is not set
    """
    if not ENCRYPTION_KEY:
        raise RuntimeError(
            "ENCRYPTION_KEY environment variable must be set for token encryption. "
            "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )

    # Derive a valid Fernet key from the encryption key
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(ENCRYPTION_KEY.encode()))
    return Fernet(key)


def encrypt_token(plaintext: str) -> str:
    """
    Encrypt a token for storage.

    Args:
        plaintext: The token to encrypt

    Returns:
        Encrypted token as base64 string

    Raises:
        RuntimeError: If ENCRYPTION_KEY is not configured
    """
    if not plaintext:
        return plaintext

    fernet = _get_fernet()
    encrypted_bytes = fernet.encrypt(plaintext.encode())
    return encrypted_bytes.decode()


def decrypt_token(ciphertext: str) -> str:
    """
    Decrypt a token from storage.

    Args:
        ciphertext: The encrypted token

    Returns:
        Decrypted token as string

    Raises:
        RuntimeError: If ENCRYPTION_KEY is not configured
        cryptography.fernet.InvalidToken: If decryption fails
    """
    if not ciphertext:
        return ciphertext

    fernet = _get_fernet()
    decrypted_bytes = fernet.decrypt(ciphertext.encode())
    return decrypted_bytes.decode()
