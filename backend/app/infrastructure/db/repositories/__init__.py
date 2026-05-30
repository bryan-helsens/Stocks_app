"""Async SQLAlchemy repository implementations.

Each repository wraps an :class:`AsyncSession` and implements the corresponding
Protocol from :mod:`app.domain.ports.repositories`. They flush (to assign PKs)
but do not commit — the unit-of-work boundary is owned by the request-scoped
session dependency (:func:`app.infrastructure.db.base.get_session`).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Asset, DividendEvent, Position, Transaction
from app.infrastructure.db import models
from app.infrastructure.db.repositories import mappers


class SqlAssetRepository:
    """Asset reference data (shared across users)."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, asset_id: UUID) -> Asset | None:
        m = await self._s.get(models.Asset, asset_id)
        return mappers.asset_to_entity(m) if m else None

    async def get_by_isin(self, isin: str) -> Asset | None:
        res = await self._s.execute(select(models.Asset).where(models.Asset.isin == isin))
        m = res.scalar_one_or_none()
        return mappers.asset_to_entity(m) if m else None

    async def get_by_ticker(self, ticker: str, exchange: str | None = None) -> Asset | None:
        stmt = select(models.Asset).where(models.Asset.ticker == ticker)
        if exchange is not None:
            stmt = stmt.where(models.Asset.exchange == exchange)
        res = await self._s.execute(stmt.limit(1))
        m = res.scalar_one_or_none()
        return mappers.asset_to_entity(m) if m else None

    async def _model_by_isin(self, isin: str) -> models.Asset | None:
        res = await self._s.execute(select(models.Asset).where(models.Asset.isin == isin))
        return res.scalar_one_or_none()

    async def _model_by_ticker(self, ticker: str, exchange: str | None) -> models.Asset | None:
        stmt = select(models.Asset).where(models.Asset.ticker == ticker)
        if exchange is not None:
            stmt = stmt.where(models.Asset.exchange == exchange)
        res = await self._s.execute(stmt.limit(1))
        return res.scalar_one_or_none()

    async def upsert(self, asset: Asset) -> Asset:
        existing: models.Asset | None = None
        if asset.isin:
            existing = await self._model_by_isin(asset.isin)
        if existing is None and asset.ticker:
            existing = await self._model_by_ticker(asset.ticker, asset.exchange)

        if existing is not None:
            existing.name = asset.name
            existing.sector = asset.sector or existing.sector
            existing.industry = asset.industry or existing.industry
            existing.country = asset.country or existing.country
            existing.currency = asset.currency or existing.currency
            existing.exchange = asset.exchange or existing.exchange
            existing.isin = asset.isin or existing.isin
            await self._s.flush()
            return mappers.asset_to_entity(existing)

        m = mappers.asset_to_model(asset)
        m.id = None  # let the DB assign the PK
        self._s.add(m)
        await self._s.flush()
        return mappers.asset_to_entity(m)

    async def search(self, query: str, limit: int = 20) -> list[Asset]:
        like = f"%{query}%"
        stmt = (
            select(models.Asset)
            .where((models.Asset.ticker.ilike(like)) | (models.Asset.name.ilike(like)))
            .limit(limit)
        )
        res = await self._s.execute(stmt)
        return [mappers.asset_to_entity(m) for m in res.scalars().all()]


class SqlTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, tx: Transaction, *, dedup_hash: str | None = None) -> Transaction:
        m = self._to_model(tx, dedup_hash=dedup_hash)
        self._s.add(m)
        await self._s.flush()
        return mappers.transaction_to_entity(m)

    async def add_many(self, txs: list[Transaction]) -> list[Transaction]:
        out = []
        for tx in txs:
            out.append(await self.add(tx))
        return out

    async def get(self, tx_id: UUID, user_id: UUID) -> Transaction | None:
        res = await self._s.execute(
            select(models.Transaction).where(
                models.Transaction.id == tx_id,
                models.Transaction.user_id == user_id,
                models.Transaction.deleted_at.is_(None),
            )
        )
        m = res.scalar_one_or_none()
        return mappers.transaction_to_entity(m) if m else None

    async def exists_by_dedup(self, user_id: UUID, dedup_hash: str) -> bool:
        res = await self._s.execute(
            select(models.Transaction.id).where(
                models.Transaction.user_id == user_id,
                models.Transaction.dedup_hash == dedup_hash,
            )
        )
        return res.first() is not None

    async def list_for_portfolio(self, portfolio_id: UUID, user_id: UUID) -> list[Transaction]:
        res = await self._s.execute(
            select(models.Transaction)
            .where(
                models.Transaction.portfolio_id == portfolio_id,
                models.Transaction.user_id == user_id,
                models.Transaction.deleted_at.is_(None),
            )
            .order_by(models.Transaction.trade_date)
        )
        return [mappers.transaction_to_entity(m) for m in res.scalars().all()]

    async def list_for_asset(
        self, portfolio_id: UUID, asset_id: UUID, user_id: UUID
    ) -> list[Transaction]:
        res = await self._s.execute(
            select(models.Transaction)
            .where(
                models.Transaction.portfolio_id == portfolio_id,
                models.Transaction.asset_id == asset_id,
                models.Transaction.user_id == user_id,
                models.Transaction.deleted_at.is_(None),
            )
            .order_by(models.Transaction.trade_date)
        )
        return [mappers.transaction_to_entity(m) for m in res.scalars().all()]

    async def soft_delete(self, tx_id: UUID, user_id: UUID) -> None:
        res = await self._s.execute(
            select(models.Transaction).where(
                models.Transaction.id == tx_id, models.Transaction.user_id == user_id
            )
        )
        m = res.scalar_one_or_none()
        if m is not None:
            m.deleted_at = datetime.now(UTC)
            await self._s.flush()

    def _to_model(self, tx: Transaction, *, dedup_hash: str | None = None) -> models.Transaction:
        return models.Transaction(
            user_id=tx.user_id,
            portfolio_id=tx.portfolio_id,
            asset_id=tx.asset_id,
            type=tx.type,
            trade_date=tx.trade_date,
            quantity=tx.quantity,
            price=tx.price,
            gross_amount=tx.gross_amount,
            fee=tx.fee,
            tax=tx.tax,
            net_amount=tx.net_amount,
            currency=tx.currency,
            fx_rate=tx.fx_rate,
            split_ratio=tx.split_ratio,
            source=tx.source,
            external_id=tx.external_id,
            dedup_hash=dedup_hash or compute_dedup_hash(tx),
            note=tx.note,
        )


class SqlPositionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, portfolio_id: UUID, asset_id: UUID) -> Position | None:
        res = await self._s.execute(
            select(models.Position).where(
                models.Position.portfolio_id == portfolio_id,
                models.Position.asset_id == asset_id,
            )
        )
        m = res.scalar_one_or_none()
        return mappers.position_to_entity(m) if m else None

    async def list_for_portfolio(self, portfolio_id: UUID, user_id: UUID) -> list[Position]:
        res = await self._s.execute(
            select(models.Position).where(
                models.Position.portfolio_id == portfolio_id,
                models.Position.user_id == user_id,
            )
        )
        return [mappers.position_to_entity(m) for m in res.scalars().all()]

    async def upsert(self, user_id: UUID, position: Position) -> Position:
        res = await self._s.execute(
            select(models.Position).where(
                models.Position.portfolio_id == position.portfolio_id,
                models.Position.asset_id == position.asset_id,
            )
        )
        m = res.scalar_one_or_none()
        if m is None:
            m = models.Position(
                user_id=user_id,
                portfolio_id=position.portfolio_id,
                asset_id=position.asset_id,
            )
            self._s.add(m)
        m.quantity = position.quantity
        m.avg_cost = position.avg_cost
        m.total_invested = position.total_invested
        m.realized_pnl = position.realized_pnl
        m.currency = position.currency
        await self._s.flush()
        return mappers.position_to_entity(m)

    async def delete(self, portfolio_id: UUID, asset_id: UUID) -> None:
        res = await self._s.execute(
            select(models.Position).where(
                models.Position.portfolio_id == portfolio_id,
                models.Position.asset_id == asset_id,
            )
        )
        m = res.scalar_one_or_none()
        if m is not None:
            await self._s.delete(m)
            await self._s.flush()


class SqlDividendRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, user_id: UUID, portfolio_id: UUID, dividend: DividendEvent) -> None:
        m = models.Dividend(
            user_id=user_id,
            portfolio_id=portfolio_id,
            asset_id=dividend.asset_id,
            ex_date=dividend.ex_date,
            pay_date=dividend.pay_date,
            amount_per_share=dividend.amount_per_share,
            shares=dividend.shares,
            gross_amount=dividend.gross_amount,
            withholding_tax=dividend.withholding_tax,
            belgian_rv=dividend.belgian_rv,
            net_amount=dividend.net_amount,
            currency=dividend.currency,
            source_country=dividend.source_country,
        )
        self._s.add(m)
        await self._s.flush()

    async def list_for_user(self, user_id: UUID, year: int | None = None) -> list[DividendEvent]:
        stmt = select(models.Dividend).where(models.Dividend.user_id == user_id)
        if year is not None:
            stmt = stmt.where(extract("year", models.Dividend.pay_date) == year)
        res = await self._s.execute(stmt.order_by(models.Dividend.pay_date))
        return [mappers.dividend_to_entity(m) for m in res.scalars().all()]

    async def list_for_asset(self, user_id: UUID, asset_id: UUID) -> list[DividendEvent]:
        res = await self._s.execute(
            select(models.Dividend).where(
                models.Dividend.user_id == user_id, models.Dividend.asset_id == asset_id
            )
        )
        return [mappers.dividend_to_entity(m) for m in res.scalars().all()]


def compute_dedup_hash(tx: Transaction) -> str:
    """Stable dedup hash used to detect duplicate transactions (BR7)."""
    key = "|".join(
        str(x)
        for x in (
            tx.user_id,
            tx.portfolio_id,
            tx.asset_id,
            tx.type,
            tx.trade_date.isoformat() if tx.trade_date else "",
            tx.quantity,
            tx.price,
            tx.gross_amount,
            tx.external_id or "",
        )
    )
    return hashlib.sha256(key.encode()).hexdigest()
