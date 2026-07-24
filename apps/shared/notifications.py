"""Pluggable notification sending.

A ``Notifier`` sends a short message somewhere. The call sites just do
``get_notifier().send(...)`` and never know (or care) where it goes — so adding a
new destination later is one new class + one line in ``build_notifier``, with
zero changes elsewhere. ``MultiNotifier`` fans out to several at once.

Currently wired: ntfy. To add e.g. Telegram, write a ``TelegramNotifier`` with a
``send`` method and append it in ``build_notifier``.
"""

import logging
from typing import Protocol, runtime_checkable

import httpx

from apps.shared.config import settings

logger = logging.getLogger(__name__)


@runtime_checkable
class Notifier(Protocol):
    """Anything that can deliver a short message."""

    def send(
        self,
        message: str,
        *,
        title: str | None = None,
        tags: list[str] | None = None,
    ) -> None: ...


class NtfyNotifier:
    """Push via ntfy (ntfy.sh or self-hosted). Zero-auth: POST to the topic URL."""

    def __init__(self, topic_url: str, timeout: float = 5.0) -> None:
        self._url = topic_url
        self._timeout = timeout

    def send(self, message, *, title=None, tags=None) -> None:
        headers: dict[str, str] = {}
        if title:
            headers["Title"] = title
        if tags:
            headers["Tags"] = ",".join(tags)
        httpx.post(
            self._url,
            content=message.encode("utf-8"),
            headers=headers,
            timeout=self._timeout,
        )


class MultiNotifier:
    """Fan out to several notifiers; one failing doesn't stop the rest."""

    def __init__(self, notifiers: list[Notifier]) -> None:
        self._notifiers = notifiers

    def send(self, message, *, title=None, tags=None) -> None:
        for n in self._notifiers:
            try:
                n.send(message, title=title, tags=tags)
            except Exception as e:
                logger.warning("notifier %s failed: %s", type(n).__name__, e)


class NullNotifier:
    """No-op sink used when nothing is configured (dev / notifications off)."""

    def send(self, message, *, title=None, tags=None) -> None:
        logger.debug("notifications disabled; dropping: %s", title or message)


def build_notifier() -> Notifier:
    """Assemble the notifier from settings. Add new providers here."""
    notifiers: list[Notifier] = []
    if settings.ntfy_url:
        notifiers.append(NtfyNotifier(settings.ntfy_url))
    # Future providers, e.g.:
    # if settings.telegram_bot_token and settings.telegram_chat_id:
    #     notifiers.append(TelegramNotifier(...))

    if not notifiers:
        return NullNotifier()
    if len(notifiers) == 1:
        return notifiers[0]
    return MultiNotifier(notifiers)


# Process-wide singleton built once from config.
notifier: Notifier = build_notifier()
