"""SMTP email notifier (implements the Notifier port).

Sends via the configured SMTP server using STARTTLS. Runs the blocking smtplib
call in a thread so it can be awaited. Missing SMTP configuration raises an
ExternalServiceError rather than silently dropping the message.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.core.errors import ExternalServiceError
from app.domain.ports.notifier import NotificationMessage


class EmailNotifier:
    channel = "EMAIL"

    async def send(self, message: NotificationMessage) -> bool:
        if not settings.SMTP_HOST:
            raise ExternalServiceError("SMTP is not configured.")
        return await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: NotificationMessage) -> bool:
        msg = EmailMessage()
        msg["From"] = settings.SMTP_FROM
        msg["To"] = message.recipient
        msg["Subject"] = message.title
        msg.set_content(message.body)

        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
                server.ehlo()
                if server.has_extn("STARTTLS"):
                    server.starttls()
                    server.ehlo()
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            raise ExternalServiceError(f"Email delivery failed: {exc}") from exc
        return True
