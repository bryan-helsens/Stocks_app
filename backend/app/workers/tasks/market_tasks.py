"""Market-data background tasks: quote refresh and EOD valuation snapshots."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select

from app.core.logging import get_logger
from app.infrastructure.db.base import get_session_factory
from app.infrastructure.db import models
from app.infrastructure.market_data import get_market_data_provider
from app.workers.celery_app import celery_app, run_async

logger = get_logger(__name__)


@celery_app.task(name="market.refresh_quotes")
def refresh_quotes() -> dict:
    """Fetch fresh quotes for all held assets and persist EOD price points."""
    return run_async(_refresh_quotes())


async def _refresh_quotes() -> dict:
    provider = get_market_data_provider()
    factory = get_session_factory()
    async with factory() as session:
        res = await session.execute(select(models.Asset).where(models.Asset.is_active.is_(True)))
        assets = list(res.scalars().all())
        tickers = [a.ticker for a in assets]
        if not tickers:
            return {"updated": 0}
        quotes = await provider.get_quotes(tickers)
        now = datetime.now(UTC)
        updated = 0
        by_ticker = {a.ticker: a for a in assets}
        for ticker, quote in quotes.items():
            asset = by_ticker.get(ticker)
            if asset is None:
                continue
            session.add(
                models.PriceHistory(asset_id=asset.id, ts=now, close=quote.price)
            )
            updated += 1
        await session.commit()
        logger.info("quotes_refreshed", updated=updated, requested=len(tickers))
        return {"updated": updated}


@celery_app.task(name="market.eod_snapshot")
def eod_snapshot() -> dict:
    """Store an end-of-day total-value snapshot per portfolio."""
    return run_async(_eod_snapshot())


async def _eod_snapshot() -> dict:
    factory = get_session_factory()
    today = date.today()
    async with factory() as session:
        res = await session.execute(
            select(models.Portfolio).where(models.Portfolio.deleted_at.is_(None))
        )
        portfolios = list(res.scalars().all())
        count = 0
        for portfolio in portfolios:
            pos_res = await session.execute(
                select(models.Position).where(models.Position.portfolio_id == portfolio.id)
            )
            positions = list(pos_res.scalars().all())
            total_cost = sum((p.total_invested for p in positions), Decimal(0))
            # Latest known close per asset for a market value estimate.
            total_value = Decimal(0)
            for p in positions:
                price_res = await session.execute(
                    select(models.PriceHistory.close)
                    .where(models.PriceHistory.asset_id == p.asset_id)
                    .order_by(models.PriceHistory.ts.desc())
                    .limit(1)
                )
                close = price_res.scalar_one_or_none()
                if close is not None:
                    total_value += p.quantity * close
            snapshot = models.PortfolioSnapshot(
                portfolio_id=portfolio.id,
                date=today,
                total_value=total_value,
                total_cost=total_cost,
                unrealized_pnl=total_value - total_cost,
                currency=portfolio.base_currency,
            )
            await session.merge(snapshot)
            count += 1
        await session.commit()
        logger.info("eod_snapshots_written", portfolios=count)
        return {"portfolios": count}
