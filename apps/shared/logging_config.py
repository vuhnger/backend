"""Structured logging via structlog.

Routes the stdlib logging that the apps already use (``logging.getLogger``) through
a structlog ProcessorFormatter, so existing ``logger.info(...)`` calls come out as
JSON in production and human-friendly console lines in development — without
rewriting a single log statement. Call ``configure_logging()`` once at startup;
the app factory does this.
"""

import logging

import structlog

from apps.shared.config import settings

# Shared processors applied to both structlog- and stdlib-originated records.
_SHARED_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]

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
