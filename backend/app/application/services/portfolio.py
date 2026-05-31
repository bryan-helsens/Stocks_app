"""Portfolio application service: CRUD and holdings valuation.

Builds the per-position view (market value, unrealized P/L, yield on cost) by
combining the stored :class:`Position` projection with live quotes from a
:class:`MarketDataProvider`. Pure financial maths is delegated to the domain
services; this layer only orchestrates and shapes data for the API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from app.core.errors import NotFoundError
from app.domain.entities import Asset, Position
from app.domain.ports.market_data import MarketDataProvider
from app.infrastructure.db import models
from app.infrastructure.db.repositories import SqlAssetRepository, SqlPositionRepository
from app.infrastructure.db.repositories.users import SqlPortfolioRepository


@dataclass(slots=True)
class HoldingView:
    """A position enriched with live price and derived metrics."""

    asset: Asset
    position: Position
    price: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None
    unrealized_pct: Decimal | None


@dataclass(slots=True)
class PortfolioSummary:
    portfolio_id: UUID
    name: str
    base_currency: str
    total_value: Decimal
    total_invested: Decimal
    total_unrealized: Decimal
    realized_pnl: Decimal
    holdings: list[HoldingView] = field(default_factory=list)


class PortfolioService:
    def __init__(
        self,
        portfolios: SqlPortfolioRepository,
        positions: SqlPositionRepository,
        assets: SqlAssetRepository,
        market_data: MarketDataProvider,
    ) -> None:
        self._portfolios = portfolios
        self._positions = positions
        self._assets = assets
        self._market = market_data

    async def create(
        self, user_id: UUID, name: str, base_currency: str = "EUR", is_default: bool = False
    ) -> models.Portfolio:
        portfolio = models.Portfolio(
            user_id=user_id, name=name, base_currency=base_currency, is_default=is_default
        )
        return await self._portfolios.create(portfolio)

    async def list(self, user_id: UUID) -> list[models.Portfolio]:
        return await self._portfolios.list_for_user(user_id)

    async def summary(self, portfolio_id: UUID, user_id: UUID) -> PortfolioSummary:
        portfolio = await self._portfolios.get(portfolio_id, user_id)
        if portfolio is None:
            raise NotFoundError("Portfolio not found.")

        positions = await self._positions.list_for_portfolio(portfolio_id, user_id)
        # Resolve assets and fetch quotes in bulk.
        assets: dict[UUID, Asset] = {}
        tickers: list[str] = []
        for pos in positions:
            asset = await self._assets.get(pos.asset_id)
            if asset is not None:
                assets[pos.asset_id] = asset
                tickers.append(asset.ticker)

        quotes = await self._market.get_quotes(tickers) if tickers else {}

        holdings: list[HoldingView] = []
        total_value = Decimal(0)
        total_invested = Decimal(0)
        total_unrealized = Decimal(0)
        realized = Decimal(0)

        for pos in positions:
            asset = assets.get(pos.asset_id)
            if asset is None:
                continue
            quote = quotes.get(asset.ticker)
            price = quote.price if quote else None
            mv = pos.market_value(price) if price is not None else None
            upl = pos.unrealized_pnl(price) if price is not None else None
            upct = (
                (upl / pos.total_invested) if (upl is not None and pos.total_invested > 0) else None
            )
            holdings.append(
                HoldingView(
                    asset=asset, position=pos, price=price,
                    market_value=mv, unrealized_pnl=upl, unrealized_pct=upct,
                )
            )
            total_invested += pos.total_invested
            realized += pos.realized_pnl
            if mv is not None:
                total_value += mv
            if upl is not None:
                total_unrealized += upl

        return PortfolioSummary(
            portfolio_id=portfolio.id,
            name=portfolio.name,
            base_currency=portfolio.base_currency,
            total_value=total_value,
            total_invested=total_invested,
            total_unrealized=total_unrealized,
            realized_pnl=realized,
            holdings=holdings,
        )
