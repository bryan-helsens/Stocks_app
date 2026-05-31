"""Port for notification channels (push, Telegram, email — M16)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class NotificationMessage:
    title: str
    body: str
    #: Channel-specific recipient (email address, chat id, device token).
    recipient: str
    data: dict | None = None


@runtime_checkable
class Notifier(Protocol):
    """Sends a single notification over one channel."""

    #: Channel identifier ("EMAIL" | "TELEGRAM" | "PUSH").
    channel: str

    async def send(self, message: NotificationMessage) -> bool:
        """Deliver *message*; return True on success, raise on hard failure."""
        ...
