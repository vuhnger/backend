"""Production logs are structured, and healthcheck polling stays out of them.

uvicorn installs handlers on its own loggers with propagate=False, so nothing it
emits ever reached the root handler this module configures. Since uvicorn's
access log is nearly everything a service emits, production logs were 100%
plain-text and 0% JSON — the structlog setup was inert where it mattered most.
"""

import logging

from apps.shared.logging_config import _UVICORN_LOGGERS, configure_logging


def _access_record(path: str) -> logging.LogRecord:
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d', None, None
    )
    record.args = ("1.2.3.4:0", "GET", path, "1.1", 200)
    return record


def test_uvicorn_loggers_are_routed_to_the_root_handler():
    configure_logging(force=True)
    for name in _UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        assert logger.handlers == [], f"{name} still writes its own plain-text lines"
        assert logger.propagate is True, f"{name} never reaches the structlog formatter"


def test_healthcheck_access_lines_are_dropped():
    configure_logging(force=True)
    access = logging.getLogger("uvicorn.access")
    # Six services polled every 15-30s would bury real traffic.
    assert not access.filter(_access_record("/site/health"))
    assert not access.filter(_access_record("/strava/openapi.json"))


def test_real_traffic_is_still_logged():
    configure_logging(force=True)
    access = logging.getLogger("uvicorn.access")
    assert access.filter(_access_record("/site/visit"))
    assert access.filter(_access_record("/projects"))
