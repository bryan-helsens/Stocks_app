"""Celery application and beat schedule.

Background processing keeps slow/external work out of the request cycle:
periodic quote refresh, end-of-day portfolio valuation, dividend detection,
alert evaluation and (heavy) report generation. Tasks are thin sync wrappers
that drive the same async services via :func:`run_async`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "divtrack",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.market_tasks",
        "app.workers.tasks.dividend_tasks",
        "app.workers.tasks.alert_tasks",
        "app.workers.tasks.report_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Brussels",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    result_expires=3600,
)

# --------------------------------------------------------------------------- #
# Periodic schedule (Celery Beat)
# --------------------------------------------------------------------------- #
celery_app.conf.beat_schedule = {
    # Refresh quotes every 15 minutes during European trading hours (Mon–Fri).
    "refresh-quotes": {
        "task": "market.refresh_quotes",
        "schedule": crontab(minute="*/15", hour="9-18", day_of_week="mon-fri"),
    },
    # End-of-day portfolio valuation snapshot.
    "eod-valuation": {
        "task": "market.eod_snapshot",
        "schedule": crontab(minute=30, hour=18, day_of_week="mon-fri"),
    },
    # Detect newly paid dividends each morning.
    "detect-dividends": {
        "task": "dividends.detect",
        "schedule": crontab(minute=0, hour=7),
    },
    # Evaluate active alerts every 10 minutes.
    "evaluate-alerts": {
        "task": "alerts.evaluate",
        "schedule": crontab(minute="*/10"),
    },
}


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine to completion from a synchronous Celery task.

    Uses a fresh event loop per call so tasks never share loop state.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
