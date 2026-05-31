"""Push notifier (implements the Notifier port).

Delivers to mobile/desktop clients via Firebase Cloud Messaging (FCM) HTTP v1 /
legacy endpoint. Kept provider-light: the device push token is the recipient.
When no push backend is configured it is a safe no-op (returns False) so alert
evaluation never crashes — email remains the reliable channel.

Telegram is intentionally **not** implemented (per product decision).
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger
from app.domain.ports.notifier import NotificationMessage

logger = get_logger(__name__)

# Legacy FCM endpoint kept for simplicity; swap for HTTP v1 + OAuth in prod.
_FCM_URL = "https://fcm.googleapis.com/fcm/send"


class PushNotifier:
    channel = "PUSH"

    def __init__(self, server_key: str | None = None) -> None:
        # Reuse a generic secret slot; production should use a dedicated setting.
        self._server_key = server_key

    async def send(self, message: NotificationMessage) -> bool:
        if not self._server_key:
            logger.info("push_skipped_no_backend", title=message.title)
            return False
        payload = {
            "to": message.recipient,
            "notification": {"title": message.title, "body": message.body},
            "data": message.data or {},
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    _FCM_URL,
                    headers={"Authorization": f"key={self._server_key}"},
                    json=payload,
                )
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("push_failed", error=str(exc))
            return False
        return True
