"""Mapping helpers between ORM models and domain entities.

Repositories use these to keep the domain layer free of SQLAlchemy types.
"""

from __future__ import annotations

from app.domain.entities import Asset, DividendEvent, Fundamentals, Position, Transaction
from app.infrastructure.db import models


def asset_to_entity(m: models.Asset) -> Asset:
    return Asset(
        id=m.id,
        ticker=m.ticker,
        name=m.name,
        asset_class=m.asset_class,
        isin=m.isin,
        sector=m.sector,
        industry=m.industry,
        country=m.country,
        currency=m.currency,
        exchange=m.exchange,
    )


def asset_to_model(e: Asset) -> models.Asset:
    return models.Asset(
        id=e.id,
        ticker=e.ticker,
        name=e.name,
        asset_class=e.asset_class,
        isin=e.isin,
        sector=e.sector,
        industry=e.industry,
        country=e.country,
        currency=e.currency,
        exchange=e.exchange,
    )


def transaction_to_entity(m: models.Transaction) -> Transaction:
    return Transaction(
        id=m.id,
        user_id=m.user_id,
        portfolio_id=m.portfolio_id,
        type=m.type,
        trade_date=m.trade_date,
        currency=m.currency,
        asset_id=m.asset_id,
        quantity=m.quantity,
        price=m.price,
        gross_amount=m.gross_amount,
        fee=m.fee,
        tax=m.tax,
        net_amount=m.net_amount,
        fx_rate=m.fx_rate,
        split_ratio=m.split_ratio,
        source=m.source,
        external_id=m.external_id,
        note=m.note,
    )


def position_to_entity(m: models.Position) -> Position:
    return Position(
        portfolio_id=m.portfolio_id,
        asset_id=m.asset_id,
        quantity=m.quantity,
        avg_cost=m.avg_cost,
        total_invested=m.total_invested,
        realized_pnl=m.realized_pnl,
        currency=m.currency,
    )


def dividend_to_entity(m: models.Dividend) -> DividendEvent:
    return DividendEvent(
        asset_id=m.asset_id,
        ex_date=m.ex_date,
        pay_date=m.pay_date,
        amount_per_share=m.amount_per_share or m.gross_amount,
        shares=m.shares or m.gross_amount,
        gross_amount=m.gross_amount,
        currency=m.currency,
        withholding_tax=m.withholding_tax,
        belgian_rv=m.belgian_rv,
        net_amount=m.net_amount,
        source_country=m.source_country,
    )


def fundamentals_to_entity(m: models.Fundamentals) -> Fundamentals:
    return Fundamentals(
        asset_id=m.asset_id,
        as_of=m.as_of,
        pe=m.pe,
        forward_pe=m.forward_pe,
        peg=m.peg,
        roe=m.roe,
        roic=m.roic,
        debt_equity=m.debt_equity,
        fcf=m.fcf,
        payout_ratio=m.payout_ratio,
        revenue_growth=m.revenue_growth,
        earnings_growth=m.earnings_growth,
        dividend_growth=m.dividend_growth,
        eps=m.eps,
        book_value=m.book_value,
    )
