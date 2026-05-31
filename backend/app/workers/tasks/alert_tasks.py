"""Alert evaluation background task (M16).

Evaluates active alerts against the latest known prices and creates
notifications (respecting a simple debounce via ``last_triggered_at``). Actual
delivery is attempted per channel via the notifier factory (email/push).
Telegram is intentionally not supported.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.logging import get_logger
from app.domain.ports.notifier import NotificationMessage
from app.domain.value_objects.enums import AlertType, NotificationStatus
from app.infrastructure.db import models
from app.infrastructure.db.base import get_session_factory
from app.infrastructure.notifications import get_notifier
from app.workers.celery_app import celery_app, run_async

logger = get_logger(__name__)

_DEBOUNCE = timedelta(hours=12)


@celery_app.task(name="alerts.evaluate")
def evaluate() -> dict:
    return run_async(_evaluate())


async def _evaluate() -> dict:
    factory = get_session_factory()
    now = datetime.now(UTC)
    async with factory() as session:
        res = await session.execute(select(models.Alert).where(models.Alert.is_active.is_(True)))
        alerts = list(res.scalars().all())
        triggered = 0
        for alert in alerts:
            if alert.last_triggered_at and now - alert.last_triggered_at < _DEBOUNCE:
                continue
            price = await _latest_price(session, alert.asset_id) if alert.asset_id else None
            if not _is_triggered(alert, price):
                continue
            title, body = _message_for(alert, price)
            for channel in alert.channels or []:
                notification = models.Notification(
                    user_id=alert.user_id,
                    alert_id=alert.id,
                    type=alert.type,
                    channel=channel,
                    title=title,
                    body=body,
                    status=NotificationStatus.PENDING,
                )
                session.add(notification)
                await _try_deliver(session, alert.user_id, channel, title, body, notification)
            alert.last_triggered_at = now
            triggered += 1
        await session.commit()
        logger.info("alerts_evaluated", count=len(alerts), triggered=triggered)
        return {"evaluated": len(alerts), "triggered": triggered}


async def _latest_price(session, asset_id) -> Decimal | None:
    res = await session.execute(
        select(models.PriceHistory.close)
        .where(models.PriceHistory.asset_id == asset_id)
        .order_by(models.PriceHistory.ts.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


def _is_triggered(alert: models.Alert, price: Decimal | None) -> bool:
    threshold = alert.threshold or {}
    if alert.type == AlertType.PRICE_TARGET and price is not None:
        target = threshold.get("price")
        if target is None:
            return False
        target = Decimal(str(target))
        direction = threshold.get("direction", "above")
        return price >= target if direction == "above" else price <= target
    # Other alert types are evaluated by their dedicated producers; default off.
    return False


def _message_for(alert: models.Alert, price: Decimal | None) -> tuple[str, str]:
    if alert.type == AlertType.PRICE_TARGET:
        return (
            "Koersdoel bereikt",
            f"De koers ({price}) heeft je ingestelde doel bereikt. "
            "Informatief — geen advies.",
        )
    return ("DivTrack melding", "Een van je alerts is geactiveerd. Informatief — geen advies.")


async def _try_deliver(session, user_id, channel, title, body, notification) -> None:
    notifier = get_notifier(channel)
    if notifier is None:
        notification.status = NotificationStatus.FAILED
        return
    recipient = await _recipient_for(session, user_id, channel)
    if not recipient:
        notification.status = NotificationStatus.FAILED
        return
    try:
        ok = await notifier.send(NotificationMessage(title=title, body=body, recipient=recipient))
        notification.status = NotificationStatus.SENT if ok else NotificationStatus.FAILED
        if ok:
            notification.sent_at = datetime.now(UTC)
    except Exception as exc:  # noqa: BLE001 - never crash the evaluation loop
        logger.warning("notification_failed", error=str(exc), channel=str(channel))
        notification.status = NotificationStatus.FAILED


async def _recipient_for(session, user_id, channel) -> str | None:
    user = await session.get(models.User, user_id)
    if user is None:
        return None
    if str(channel).upper() == "EMAIL":
        return user.email
    if str(channel).upper() == "PUSH":
        res = await session.execute(
            select(models.Device.push_token).where(
                models.Device.user_id == user_id,
                models.Device.revoked_at.is_(None),
                models.Device.push_token.is_not(None),
            ).limit(1)
        )
        return res.scalar_one_or_none()
    return None
