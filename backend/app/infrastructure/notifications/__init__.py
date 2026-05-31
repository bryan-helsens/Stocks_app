"""Notification channel factory (email + push).

Telegram is intentionally not supported. New channels implement the
:class:`app.domain.ports.notifier.Notifier` port and register here.
"""

from __future__ import annotations

from app.domain.ports.notifier import Notifier
from app.domain.value_objects.enums import AlertChannel
from app.infrastructure.notifications.email import EmailNotifier
from app.infrastructure.notifications.push import PushNotifier


def get_notifier(channel: AlertChannel | str) -> Notifier | None:
    """Return a notifier for *channel*, or None if unsupported/disabled."""
    name = str(channel).upper()
    if name == AlertChannel.EMAIL:
        return EmailNotifier()
    if name == AlertChannel.PUSH:
        return PushNotifier()
    # AlertChannel.TELEGRAM is deliberately unsupported.
    return None
