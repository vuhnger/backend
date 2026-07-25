"""Centralized, typed configuration.

Replaces scattered ``os.getenv`` calls with a single validated ``Settings``
object. Fields are optional at the type level because the four apps need
different subsets (n8n needs no DB or secrets); each module still asserts the
specific values it requires, so the fail-fast behaviour is preserved while the
config lives in one typed place.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Read from real environment variables only. In every deployment the process
    # env is populated (docker compose `env_file: .env` / `environment:`), so
    # Settings doesn't parse .env itself — which also keeps tests hermetic.
    model_config = SettingsConfigDict(extra="ignore")

    # Runtime
    environment: str = "development"

    # Database
    database_url: str | None = None
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800

    # Security / auth
    internal_api_key: str | None = None
    state_secret: str | None = None
    encryption_key: str | None = None

    # Frontend / CORS
    frontend_url: str | None = None

    # Rate limiting
    rate_limit_default: str = "120/minute"
    rate_limit_storage_uri: str | None = None

    # Strava OAuth. The owner id is optional: the first account to authorize
    # becomes the owner, and every later callback must match it. Set it explicitly
    # only to re-establish ownership after the auth row has been wiped.
    strava_client_id: str | None = None
    strava_client_secret: str | None = None
    strava_redirect_uri: str | None = None
    strava_owner_athlete_id: str | None = None

    # WakaTime OAuth (same ownership rule as Strava above).
    wakatime_client_id: str | None = None
    wakatime_client_secret: str | None = None
    wakatime_redirect_uri: str | None = None
    wakatime_owner_user_id: str | None = None

    # Projects uploads
    upload_dir: str = "/home/rocky/uploads/projects"
    upload_base_url: str = "https://api.vuhnger.dev/uploads/projects"

    # Notifications — ntfy topic URL, e.g. https://ntfy.sh/<secret-topic>.
    # (Add telegram_/discord_ fields here as more providers are wired.)
    ntfy_url: str | None = None

    # Visit notifications
    visit_notify_throttle_seconds: int = 3600  # at most one ping per IP per hour
    visit_notify_exclude_ips: str = ""         # comma-separated IPs to ignore (e.g. yours)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def excluded_visit_ips(self) -> set[str]:
        return {ip.strip() for ip in self.visit_notify_exclude_ips.split(",") if ip.strip()}


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings singleton (cached)."""
    return Settings()


# Convenience singleton for module-level reads.
settings = get_settings()
