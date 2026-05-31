"""Watchlist & alert schemas (M15/M16)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.domain.value_objects.enums import AlertChannel, AlertType
from app.schemas.common import ORMModel


class WatchlistCreate(BaseModel):
    name: str


class WatchlistResponse(ORMModel):
    id: UUID
    name: str


class WatchlistItemCreate(BaseModel):
    asset_id: UUID
    target_price: Decimal | None = None
    fair_value_alert: bool = False
    dividend_alert: bool = False
    note: str | None = None


class WatchlistItemResponse(ORMModel):
    id: UUID
    asset_id: UUID
    target_price: Decimal | None = None
    fair_value_alert: bool
    dividend_alert: bool
    note: str | None = None


class AlertCreate(BaseModel):
    type: AlertType
    asset_id: UUID | None = None
    portfolio_id: UUID | None = None
    threshold: dict | None = None
    channels: list[AlertChannel] = []


class AlertResponse(ORMModel):
    id: UUID
    type: AlertType
    asset_id: UUID | None = None
    portfolio_id: UUID | None = None
    threshold: dict | None = None
    channels: list[AlertChannel]
    is_active: bool
