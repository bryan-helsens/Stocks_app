"""Seed reference data: system brokers and a few demo assets.

Idempotent — safe to run repeatedly. Invoke with::

    python -m scripts.seed_db
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.domain.value_objects.enums import AssetClass
from app.infrastructure.db.base import get_session_factory
from app.infrastructure.db import models

_BROKERS = [
    {"name": "BUX", "slug": "bux", "country": "NL", "default_currency": "EUR", "parser_key": "bux"},
    {"name": "Generic CSV", "slug": "csv", "country": None, "default_currency": "EUR",
     "parser_key": "csv_generic"},
]

_ASSETS = [
    {"ticker": "AAPL", "isin": "US0378331005", "name": "Apple Inc.",
     "asset_class": AssetClass.STOCK, "sector": "Technology", "country": "US", "currency": "USD"},
    {"ticker": "MSFT", "isin": "US5949181045", "name": "Microsoft Corp.",
     "asset_class": AssetClass.STOCK, "sector": "Technology", "country": "US", "currency": "USD"},
    {"ticker": "O", "isin": "US7561091049", "name": "Realty Income",
     "asset_class": AssetClass.REIT, "sector": "Real Estate", "country": "US", "currency": "USD"},
    {"ticker": "VWCE", "isin": "IE00BK5BQT80", "name": "Vanguard FTSE All-World",
     "asset_class": AssetClass.ETF, "sector": None, "country": "IE", "currency": "EUR"},
]


async def seed() -> None:
    factory = get_session_factory()
    async with factory() as session:
        for broker in _BROKERS:
            exists = await session.execute(
                select(models.Broker).where(models.Broker.slug == broker["slug"])
            )
            if exists.scalar_one_or_none() is None:
                session.add(models.Broker(**broker))

        for asset in _ASSETS:
            exists = await session.execute(
                select(models.Asset).where(models.Asset.isin == asset["isin"])
            )
            if exists.scalar_one_or_none() is None:
                session.add(models.Asset(**asset))

        await session.commit()
    print("Seed complete: brokers and demo assets ensured.")


if __name__ == "__main__":
    asyncio.run(seed())
