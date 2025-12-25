"""
Strava database models for OAuth tokens and cached statistics
"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, JSON, func
from apps.shared.database import Base
from apps.shared.encryption import encrypt_token, decrypt_token


class StravaAuth(Base):
    """
    Single-row table for storing OAuth tokens (single user mode).
    Only one row should ever exist with id=1.
    Tokens are encrypted at rest using application-level encryption.
    """
    __tablename__ = "strava_auth"

    id = Column(Integer, primary_key=True)  # Always 1 for single user
    athlete_id = Column(BigInteger, nullable=False, index=True)
    _access_token = Column("access_token", String(500), nullable=False)
    _refresh_token = Column("refresh_token", String(500), nullable=False)
    expires_at = Column(Integer, nullable=False)  # Unix timestamp
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @property
    def access_token(self) -> str:
        """
        Decrypt access token on read.

        Handles both encrypted and unencrypted tokens to support migration.
        If decryption fails (legacy unencrypted token), returns value as-is.
        """
        try:
            return decrypt_token(self._access_token)
        except Exception:
            # Fallback for legacy unencrypted tokens during migration
            return self._access_token

    @access_token.setter
    def access_token(self, value: str):
        """Encrypt access token on write"""
        self._access_token = encrypt_token(value)

    @property
    def refresh_token(self) -> str:
        """
        Decrypt refresh token on read.

        Handles both encrypted and unencrypted tokens to support migration.
        If decryption fails (legacy unencrypted token), returns value as-is.
        """
        try:
            return decrypt_token(self._refresh_token)
        except Exception:
            # Fallback for legacy unencrypted tokens during migration
            return self._refresh_token

    @refresh_token.setter
    def refresh_token(self, value: str):
        """Encrypt refresh token on write"""
        self._refresh_token = encrypt_token(value)


class StravaStats(Base):
    """
    Cached Strava statistics to avoid hitting rate limits.
    Different stats_type values: ytd, recent_activities, monthly
    """
    __tablename__ = "strava_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stats_type = Column(String(50), nullable=False, unique=True, index=True)
    data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "type": self.stats_type,
            "data": self.data,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None
        }
