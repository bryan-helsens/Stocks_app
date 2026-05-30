"""Market data adapters and a provider factory.

Implements the :class:`MarketDataProvider` port. ``yfinance`` is the default
free adapter; ``null`` is a safe no-op used in tests/offline mode and when no
provider is configured. New providers (FMP, Alpha Vantage, EOD) plug in here
without touching the rest of the system.
"""

from __future__ import annotations

from datetime import date

from app.core.config import settings
from app.domain.ports.market_data import AssetInfo, MarketDataProvider, PriceBar, Quote


class NullMarketDataProvider:
    """A provider that returns no data — keeps the app fully functional offline."""

    async def get_quote(self, symbol: str) -> Quote | None:
        return None

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        return {}

    async def get_history(self, symbol: str, start: date, end: date) -> list[PriceBar]:
        return []

    async def search(self, query: str) -> list[AssetInfo]:
        return []

    async def resolve(
        self, *, ticker: str | None = None, isin: str | None = None
    ) -> AssetInfo | None:
        return None


def get_market_data_provider() -> MarketDataProvider:
    """Return the configured market-data provider instance.

    Falls back to :class:`NullMarketDataProvider` when the chosen provider's
    dependency is unavailable, so the API never fails to start because of an
    optional data source.
    """
    provider = settings.MARKET_DATA_PROVIDER.lower()
    if provider == "yfinance":
        try:
            from app.infrastructure.market_data.yfinance_provider import YFinanceProvider

            return YFinanceProvider()
        except Exception:  # pragma: no cover - optional dependency / offline
            return NullMarketDataProvider()
    return NullMarketDataProvider()
