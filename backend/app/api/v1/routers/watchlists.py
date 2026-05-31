"""Watchlist & alert endpoints (M15/M16).

Straightforward owner-scoped CRUD. Alert *evaluation* and notification delivery
happen in the Celery worker (alerts.evaluate); these endpoints manage the rules.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.errors import NotFoundError
from app.infrastructure.db import models
from app.schemas.common import Message
from app.schemas.watchlist import (
    AlertCreate,
    AlertResponse,
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemResponse,
    WatchlistResponse,
)

router = APIRouter(tags=["watchlists"])


# --------------------------------------------------------------------------- #
# Watchlists
# --------------------------------------------------------------------------- #
@router.post("/watchlists", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    body: WatchlistCreate, user: CurrentUser, session: SessionDep
) -> WatchlistResponse:
    wl = models.Watchlist(user_id=user.id, name=body.name)
    session.add(wl)
    await session.flush()
    return WatchlistResponse.model_validate(wl)


@router.get("/watchlists", response_model=list[WatchlistResponse])
async def list_watchlists(user: CurrentUser, session: SessionDep) -> list[WatchlistResponse]:
    res = await session.execute(
        select(models.Watchlist).where(models.Watchlist.user_id == user.id)
    )
    return [WatchlistResponse.model_validate(w) for w in res.scalars().all()]


async def _owned_watchlist(session, user_id: UUID, watchlist_id: UUID) -> models.Watchlist:
    wl = await session.get(models.Watchlist, watchlist_id)
    if wl is None or wl.user_id != user_id:
        raise NotFoundError("Watchlist not found.")
    return wl


@router.post("/watchlists/{watchlist_id}/items", response_model=WatchlistItemResponse,
             status_code=status.HTTP_201_CREATED)
async def add_item(
    watchlist_id: UUID, body: WatchlistItemCreate, user: CurrentUser, session: SessionDep
) -> WatchlistItemResponse:
    await _owned_watchlist(session, user.id, watchlist_id)
    item = models.WatchlistItem(
        watchlist_id=watchlist_id,
        asset_id=body.asset_id,
        target_price=body.target_price,
        fair_value_alert=body.fair_value_alert,
        dividend_alert=body.dividend_alert,
        note=body.note,
    )
    session.add(item)
    await session.flush()
    return WatchlistItemResponse.model_validate(item)


@router.get("/watchlists/{watchlist_id}/items", response_model=list[WatchlistItemResponse])
async def list_items(
    watchlist_id: UUID, user: CurrentUser, session: SessionDep
) -> list[WatchlistItemResponse]:
    await _owned_watchlist(session, user.id, watchlist_id)
    res = await session.execute(
        select(models.WatchlistItem).where(models.WatchlistItem.watchlist_id == watchlist_id)
    )
    return [WatchlistItemResponse.model_validate(i) for i in res.scalars().all()]


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #
@router.post("/alerts", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(body: AlertCreate, user: CurrentUser, session: SessionDep) -> AlertResponse:
    alert = models.Alert(
        user_id=user.id,
        type=body.type,
        asset_id=body.asset_id,
        portfolio_id=body.portfolio_id,
        threshold=body.threshold,
        channels=[c.value for c in body.channels],
    )
    session.add(alert)
    await session.flush()
    return AlertResponse.model_validate(alert)


@router.get("/alerts", response_model=list[AlertResponse])
async def list_alerts(user: CurrentUser, session: SessionDep) -> list[AlertResponse]:
    res = await session.execute(select(models.Alert).where(models.Alert.user_id == user.id))
    return [AlertResponse.model_validate(a) for a in res.scalars().all()]


@router.delete("/alerts/{alert_id}", response_model=Message)
async def delete_alert(alert_id: UUID, user: CurrentUser, session: SessionDep) -> Message:
    alert = await session.get(models.Alert, alert_id)
    if alert is None or alert.user_id != user.id:
        raise NotFoundError("Alert not found.")
    await session.delete(alert)
    return Message(message="Alert deleted.")
