"""Guards on how host configuration actually reaches the app.

Two failure modes are covered, both of which shipped to production once:

1. A setting exists in ``Settings`` but is never listed in the compose
   service's ``environment:`` block, so the host .env can't reach the
   container at all.
2. A variable is listed in compose but missing from the host .env, so Compose
   expands it to ``""`` and pydantic rejects it at import time.
"""

from pathlib import Path

import pytest
import yaml

from apps.shared.config import Settings

COMPOSE_FILE = Path(__file__).resolve().parents[1] / "docker-compose.yml"

# Settings the heatmap depends on. Absent from the container's environment the
# endpoint can only answer 503, which is exactly the outage this test exists to
# prevent from recurring silently.
HEATMAP_ENV_VARS = (
    "STRAVA_HOME_LAT",
    "STRAVA_HOME_LNG",
    "STRAVA_PRIVACY_RADIUS_M",
)


@pytest.fixture(scope="module")
def strava_service_env() -> dict[str, str]:
    compose = yaml.safe_load(COMPOSE_FILE.read_text())
    service = compose["services"]["strava-api"]
    # A service using env_file passes the whole file through and needs no
    # allowlist; this assertion pins the assumption the test rests on.
    assert "env_file" not in service, (
        "strava-api gained an env_file; the explicit allowlist below is no "
        "longer the only path for host config and this test needs rethinking"
    )
    return service["environment"]


@pytest.mark.parametrize("var", HEATMAP_ENV_VARS)
def test_heatmap_settings_are_passed_into_the_container(strava_service_env, var):
    assert var in strava_service_env, (
        f"{var} is read by Settings but not listed in strava-api's environment: "
        f"block, so it can never reach the process"
    )

    # Presence alone isn't enough: the entry has to actually substitute the
    # host variable of the same name. A hardcoded literal or a typo in the
    # ${...} spelling would satisfy the check above while still starving the
    # container. Prefix rather than equality, since a `:-default` suffix is
    # legitimate.
    value = strava_service_env[var]
    assert isinstance(value, str) and value.startswith(f"${{{var}"), (
        f"{var} is listed but resolves to {value!r} instead of substituting "
        f"the host variable of the same name"
    )


def _settings_with_env(monkeypatch, **env: str) -> Settings:
    """Build Settings from real process env.

    Deliberately not ``Settings(**kwargs)``: init kwargs are matched against
    field names, so the SCREAMING_CASE spelling would be silently discarded as
    an extra and every assertion below would pass against defaults instead of
    against the value under test.

    Every heatmap variable is cleared first. setenv only overrides what a test
    names, so a developer with STRAVA_HOME_LNG exported in their shell would
    otherwise turn the half-configured case into a fully configured one and the
    test would pass while asserting the opposite of what it claims.
    """
    for key in HEATMAP_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings()


def test_blank_coordinates_degrade_to_unset_rather_than_crashing(monkeypatch):
    # What Compose sends for a ${VAR} that the host .env doesn't define.
    settings = _settings_with_env(
        monkeypatch,
        STRAVA_HOME_LAT="",
        STRAVA_HOME_LNG="",
        STRAVA_PRIVACY_RADIUS_M="",
    )

    assert settings.strava_home_lat is None
    assert settings.strava_home_lng is None
    assert settings.strava_home_coordinate is None
    # Blank must fall back to the declared default, not to zero -- a zero radius
    # would disable clipping entirely.
    assert settings.strava_privacy_radius_m == 500.0


def test_half_configured_coordinate_is_still_treated_as_unconfigured(monkeypatch):
    settings = _settings_with_env(
        monkeypatch, STRAVA_HOME_LAT="59.939383", STRAVA_HOME_LNG=""
    )

    assert settings.strava_home_lat == 59.939383
    assert settings.strava_home_coordinate is None


def test_blank_does_not_mask_a_genuinely_invalid_value(monkeypatch):
    with pytest.raises(ValueError, match="between -90 and 90"):
        _settings_with_env(monkeypatch, STRAVA_HOME_LAT="91.0")


def test_blank_does_not_mask_an_unparseable_value(monkeypatch):
    with pytest.raises(ValueError, match="valid number"):
        _settings_with_env(monkeypatch, STRAVA_HOME_LNG="not-a-number")


def test_real_values_still_parse(monkeypatch):
    settings = _settings_with_env(
        monkeypatch,
        STRAVA_HOME_LAT="59.939383",
        STRAVA_HOME_LNG="10.649669",
        STRAVA_PRIVACY_RADIUS_M="750",
    )

    assert settings.strava_home_coordinate == (59.939383, 10.649669)
    assert settings.strava_privacy_radius_m == 750.0
