"""Portfolio & holdings schemas."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.value_objects.enums import AssetClass
from app.schemas.common import ORMModel


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_currency: str = Field(default="EUR", min_length=3, max_length=3)
    is_default: bool = False


class PortfolioResponse(ORMModel):
    id: UUID
    name: str
    description: str | None = None
    base_currency: str
    is_default: bool


class AssetResponse(BaseModel):
    id: UUID | None
    ticker: str
    name: str
    asset_class: AssetClass
    isin: str | None = None
    sector: str | None = None
    country: str | None = None
    currency: str = "USD"


class HoldingResponse(BaseModel):
    asset: AssetResponse
    quantity: Decimal
    avg_cost: Decimal
    total_invested: Decimal
    realized_pnl: Decimal
    price: Decimal | None = None
    market_value: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    unrealized_pct: Decimal | None = None


class PortfolioSummaryResponse(BaseModel):
    portfolio_id: UUID
    name: str
    base_currency: str
    total_value: Decimal
    total_invested: Decimal
    total_unrealized: Decimal
    realized_pnl: Decimal
    holdings: list[HoldingResponse]
