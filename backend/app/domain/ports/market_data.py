"""Ports for market data and fundamentals providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.domain.entities import Fundamentals


@dataclass(slots=True)
class Quote:
    """A current price quote for a single instrument."""

    symbol: str
    price: Decimal
    currency: str
    change: Decimal | None = None
    change_pct: Decimal | None = None
    as_of: date | None = None


@dataclass(slots=True)
class PriceBar:
    """A single OHLCV bar."""

    ts: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None = None


@dataclass(slots=True)
class AssetInfo:
    """Reference metadata about an instrument (for search/resolution)."""

    symbol: str
    name: str
    asset_class: str
    isin: str | None = None
    currency: str = "USD"
    exchange: str | None = None
    sector: str | None = None
    country: str | None = None


@runtime_checkable
class MarketDataProvider(Protocol):
    """Source of live quotes, historical prices and symbol search."""

    async def get_quote(self, symbol: str) -> Quote | None: ...

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]: ...

    async def get_history(
        self, symbol: str, start: date, end: date
    ) -> list[PriceBar]: ...

    async def search(self, query: str) -> list[AssetInfo]: ...

    async def resolve(self, *, ticker: str | None = None, isin: str | None = None) -> AssetInfo | None: ...


@runtime_checkable
class FundamentalsProvider(Protocol):
    """Source of company fundamentals/ratios and dividend history."""

    async def get_fundamentals(self, symbol: str) -> Fundamentals | None: ...

    async def get_dividend_history(
        self, symbol: str
    ) -> list[tuple[date, Decimal]]: ...
