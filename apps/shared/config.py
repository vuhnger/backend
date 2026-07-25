"""Centralized, typed configuration.

Replaces scattered ``os.getenv`` calls with a single validated ``Settings``
object. Fields are optional at the type level because the four apps need
different subsets (n8n needs no DB or secrets); each module still asserts the
specific values it requires, so the fail-fast behaviour is preserved while the
config lives in one typed place.
"""

from functools import lru_cache
from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Read from real environment variables only. In every deployment the process
    # env is populated (docker compose `env_file: .env` / `environment:`), so
    # Settings doesn't parse .env itself — which also keeps tests hermetic.
    model_config = SettingsConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _blank_means_unset(cls, data: Any) -> Any:
        """Treat an empty environment variable as absent.

        Compose expands an unset ``${VAR}`` to the empty string rather than
        omitting it, so a value merely missing from the host .env arrives here
        as ``""``. For the str fields that is harmless, but for a numeric one
        pydantic raises at import time — and because this module builds its
        singleton at import, that turns a forgotten .env line into a
        crash-looping container instead of the intended graceful degradation.
        Dropping blanks lets every field fall back to its declared default.
        """
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if not (isinstance(v, str) and v == "")}
        return data

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

    # Largest request body any app will accept, in bytes. Sized just above the
    # projects app's 10 MB image limit to leave room for multipart overhead;
    # everything else needs far less.
    max_request_body_bytes: int = 11 * 1024 * 1024

    # Strava OAuth. The owner id is optional: the first account to authorize
    # becomes the owner, and every later callback must match it. Set it explicitly
    # only to re-establish ownership after the auth row has been wiped.
    strava_client_id: str | None = None
    strava_client_secret: str | None = None
    strava_redirect_uri: str | None = None
    strava_owner_athlete_id: str | None = None

    # Strava heatmap privacy.
    #
    # Route tracks are absolute WGS84 and end up on a public page, so everything
    # within `strava_privacy_radius_m` of the home coordinate is clipped out of
    # every track before it is aggregated. Both values live here and are never
    # echoed in any response — publishing the radius would let a caller
    # triangulate the centre it was measured from.
    #
    # No default coordinate exists on purpose: /strava/heatmap refuses to serve
    # (503) rather than emit unclipped tracks if this is unconfigured.
    strava_home_lat: float | None = None
    strava_home_lng: float | None = None
    strava_privacy_radius_m: float = 500.0

    # WakaTime OAuth (same ownership rule as Strava above).
    wakatime_client_id: str | None = None
    wakatime_client_secret: str | None = None
    wakatime_redirect_uri: str | None = None
    wakatime_owner_user_id: str | None = None

    # n8n upstream the health proxy checks. Was hardcoded in apps/n8n/main.py.
    n8n_url: str | None = "https://n8n.vuhnger.dev"

    # Projects uploads
    upload_dir: str = "/home/rocky/uploads/projects"
    upload_base_url: str = "https://api.vuhnger.dev/uploads/projects"

    # Notifications — ntfy topic URL, e.g. https://ntfy.sh/<secret-topic>.
    # (Add telegram_/discord_ fields here as more providers are wired.)
    ntfy_url: str | None = None

    # Visit notifications
    visit_notify_throttle_seconds: int = 3600  # at most one ping per IP per hour
    visit_notify_exclude_ips: str = ""         # comma-separated IPs to ignore (e.g. yours)

    # Live cursor presence (WebSocket). Every cap below is *per process*: the hub
    # is in-memory, so two workers would each enforce its own limit and peers in
    # the same room would never see each other. Single worker is a precondition,
    # the same one the in-memory rate limiter already relies on.
    cursor_max_connections: int = 200   # across every room in this process
    cursor_max_per_room: int = 50
    cursor_max_per_ip: int = 5          # one person's open tabs, not one person's site
    cursor_max_rooms: int = 100
    # Outbound batch rate. Clients may move the mouse at 60+ Hz; we collapse that
    # to one frame per tick, so bandwidth scales with peers, not with mouse events.
    cursor_tick_hz: float = 15.0
    # Inbound cap per connection. Above it the socket is closed rather than
    # throttled: a client past 60 msg/s is broken or hostile, not merely eager.
    cursor_max_messages_per_second: float = 60.0
    # Closed after this long without a single frame from the client. A backgrounded
    # tab stops pinging and drops out, which is the correct presence semantic —
    # protocol-level keepalive alone would hold its slot for hours.
    cursor_idle_timeout_seconds: float = 900.0
    # Frames buffered for a slow client before we give up on it. 64 at 15 Hz is
    # ~4 s of backlog; anything further behind is a dead socket the OS hasn't
    # noticed yet, and holding its queue only delays reclaiming the slot.
    cursor_send_queue_size: int = 64

    # IP -> location lookup for the visit notification. `{ip}` is substituted with
    # a validated address. The default provider's free tier is HTTP-only; point
    # this at an HTTPS provider to stop leaking visitor IPs in the clear.
    geo_lookup_url: str = "http://ip-api.com/json/{ip}"

    @field_validator("strava_home_lat")
    @classmethod
    def _check_lat(cls, v: float | None) -> float | None:
        if v is not None and not -90.0 <= v <= 90.0:
            raise ValueError("STRAVA_HOME_LAT must be between -90 and 90")
        return v

    @field_validator("strava_home_lng")
    @classmethod
    def _check_lng(cls, v: float | None) -> float | None:
        if v is not None and not -180.0 <= v <= 180.0:
            raise ValueError("STRAVA_HOME_LNG must be between -180 and 180")
        return v

    @field_validator("strava_privacy_radius_m")
    @classmethod
    def _check_radius(cls, v: float) -> float:
        # A zero or negative radius would silently disable the clipping that the
        # whole feature depends on, so it's a startup error rather than a no-op.
        if v <= 0:
            raise ValueError("STRAVA_PRIVACY_RADIUS_M must be greater than 0")
        return v

    @field_validator(
        "cursor_max_connections",
        "cursor_max_per_room",
        "cursor_max_per_ip",
        "cursor_max_rooms",
        "cursor_tick_hz",
        "cursor_max_messages_per_second",
        "cursor_idle_timeout_seconds",
        "cursor_send_queue_size",
    )
    @classmethod
    def _check_positive(cls, v: float, info) -> float:
        # Zero is the dangerous value, not negative: CURSOR_TICK_HZ=0 divides by
        # zero in the broadcast loop and CURSOR_MAX_CONNECTIONS=0 rejects every
        # visitor — both are misconfigurations that should stop the process at
        # startup rather than surface as a silently dead feature.
        if v <= 0:
            raise ValueError(f"{info.field_name.upper()} must be greater than 0")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def strava_home_coordinate(self) -> tuple[float, float] | None:
        """Home ``(lat, lng)``, or None when the pair isn't fully configured.

        Both halves are required: a latitude without a longitude is a
        misconfiguration, and treating it as "partially set" would be the one
        way untrimmed tracks could slip out.
        """
        if self.strava_home_lat is None or self.strava_home_lng is None:
            return None
        return (self.strava_home_lat, self.strava_home_lng)

    @property
    def excluded_visit_ips(self) -> set[str]:
        return {ip.strip() for ip in self.visit_notify_exclude_ips.split(",") if ip.strip()}


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings singleton (cached)."""
    return Settings()


# Convenience singleton for module-level reads.
settings = get_settings()
