"""Structured logging via structlog.

Routes the stdlib logging that the apps already use (``logging.getLogger``) through
a structlog ProcessorFormatter, so existing ``logger.info(...)`` calls come out as
JSON in production and human-friendly console lines in development — without
rewriting a single log statement. Call ``configure_logging()`` once at startup;
the app factory does this.
"""

import logging

import structlog
from structlog.typing import Processor

from apps.shared.config import settings

# Shared processors applied to both structlog- and stdlib-originated records.
_SHARED_PROCESSORS: list[Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]

# uvicorn installs handlers on its own loggers with propagate=False, so its output
# never reaches the root handler configured below. Since uvicorn's access log is
# the overwhelming majority of what a service emits, that meant production logs
# were 100% plain-text uvicorn lines and 0% of the JSON this module exists to
# produce. Clearing those handlers hands the records back to the root logger.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")

# Container healthchecks poll these every 15-30s across six services. Left in,
# they bury real traffic; the healthcheck's own verdict is what reports on them.
_NOISY_SUFFIXES = ("/health", "/openapi.json")


class _DropHealthchecks(logging.Filter):
    """Drop uvicorn access records for healthcheck polling."""

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn.access logs with args = (client, method, path, http_version, status)
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            return not str(args[2]).endswith(_NOISY_SUFFIXES)
        return True


_configured = False


def configure_logging(force: bool = False) -> None:
    """Configure structlog + stdlib logging. Idempotent (safe to call per app)."""
    global _configured
    if _configured and not force:
        return

    renderer = (
        structlog.processors.JSONRenderer()
        if settings.is_production
        else structlog.dev.ConsoleRenderer()
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Route uvicorn's own output through the formatter above instead of letting
    # it write its default plain-text lines straight to stderr.
    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    logging.getLogger("uvicorn.access").addFilter(_DropHealthchecks())

    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None):
    """Return a structlog logger. Prefer this for new code (supports kwargs)."""
    return structlog.get_logger(name)
