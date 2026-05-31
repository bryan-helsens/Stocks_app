"""yfinance-backed market data provider.

Wraps the (synchronous) ``yfinance`` library in a thread executor so it can be
awaited from async code. Network/parsing errors degrade gracefully to ``None``
rather than failing the request.
"""

from __future__ import annotations

import asyncio
from datetime import date

from app.domain.ports.market_data import AssetInfo, PriceBar, Quote
from app.domain.value_objects.money import to_decimal


class YFinanceProvider:
    """Implements :class:`MarketDataProvider` using yfinance."""

    def __init__(self) -> None:
        import yfinance  # noqa: F401  (import here so the factory can catch ImportError)

    async def get_quote(self, symbol: str) -> Quote | None:
        return (await self.get_quotes([symbol])).get(symbol)

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        if not symbols:
            return {}
        return await asyncio.to_thread(self._get_quotes_sync, symbols)

    def _get_quotes_sync(self, symbols: list[str]) -> dict[str, Quote]:
        import yfinance as yf

        out: dict[str, Quote] = {}
        tickers = yf.Tickers(" ".join(symbols))
        for sym in symbols:
            try:
                info = tickers.tickers[sym].fast_info
                price = info.get("last_price") or info.get("lastPrice")
                if price is None:
                    continue
                prev = info.get("previous_close") or info.get("previousClose")
                change = None
                change_pct = None
                if prev:
                    change = to_decimal(price) - to_decimal(prev)
                    change_pct = change / to_decimal(prev)
                out[sym] = Quote(
                    symbol=sym,
                    price=to_decimal(price),
                    currency=info.get("currency", "USD"),
                    change=change,
                    change_pct=change_pct,
                    as_of=date.today(),
                )
            except Exception:  # pragma: no cover - per-symbol resilience
                continue
        return out

    async def get_history(self, symbol: str, start: date, end: date) -> list[PriceBar]:
        return await asyncio.to_thread(self._get_history_sync, symbol, start, end)

    def _get_history_sync(self, symbol: str, start: date, end: date) -> list[PriceBar]:
        import yfinance as yf

        bars: list[PriceBar] = []
        try:
            df = yf.Ticker(symbol).history(start=start.isoformat(), end=end.isoformat())
            for ts, row in df.iterrows():
                bars.append(
                    PriceBar(
                        ts=ts.date(),
                        open=to_decimal(row["Open"]),
                        high=to_decimal(row["High"]),
                        low=to_decimal(row["Low"]),
                        close=to_decimal(row["Close"]),
                        volume=int(row["Volume"]) if row["Volume"] else None,
                    )
                )
        except Exception:  # pragma: no cover
            return []
        return bars

    async def search(self, query: str) -> list[AssetInfo]:
        # yfinance has no robust search endpoint; resolution is by exact symbol.
        info = await self.resolve(ticker=query)
        return [info] if info else []

    async def resolve(
        self, *, ticker: str | None = None, isin: str | None = None
    ) -> AssetInfo | None:
        symbol = ticker or isin
        if not symbol:
            return None
        return await asyncio.to_thread(self._resolve_sync, symbol)

    def _resolve_sync(self, symbol: str) -> AssetInfo | None:
        import yfinance as yf

        try:
            t = yf.Ticker(symbol)
            info = t.info
            if not info or "symbol" not in info:
                return None
            return AssetInfo(
                symbol=info.get("symbol", symbol),
                name=info.get("longName") or info.get("shortName") or symbol,
                asset_class=_map_class(info.get("quoteType", "EQUITY")),
                isin=info.get("isin"),
                currency=info.get("currency", "USD"),
                exchange=info.get("exchange"),
                sector=info.get("sector"),
                country=info.get("country"),
            )
        except Exception:  # pragma: no cover
            return None


def _map_class(quote_type: str) -> str:
    mapping = {
        "EQUITY": "STOCK",
        "ETF": "ETF",
        "MUTUALFUND": "ETF",
        "CRYPTOCURRENCY": "CRYPTO",
        "BOND": "BOND",
    }
    return mapping.get(quote_type.upper(), "STOCK")
