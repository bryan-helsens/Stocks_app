"""Repository ports.

These Protocols describe the persistence operations the application layer needs,
expressed in terms of domain entities. Concrete async SQLAlchemy implementations
live in ``app.infrastructure.db.repositories``. Keeping them abstract lets the
service layer be unit-tested against in-memory fakes.

Note: implementations operate within a unit-of-work (an async DB session passed
at construction); transaction boundaries are managed by the application layer.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import (
    Asset,
    DividendEvent,
    Fundamentals,
    Position,
    Transaction,
)


@runtime_checkable
class AssetRepository(Protocol):
    async def get(self, asset_id: UUID) -> Asset | None: ...
    async def get_by_isin(self, isin: str) -> Asset | None: ...
    async def get_by_ticker(self, ticker: str, exchange: str | None = None) -> Asset | None: ...
    async def upsert(self, asset: Asset) -> Asset: ...
    async def search(self, query: str, limit: int = 20) -> list[Asset]: ...


@runtime_checkable
class TransactionRepository(Protocol):
    async def add(self, tx: Transaction) -> Transaction: ...
    async def add_many(self, txs: list[Transaction]) -> list[Transaction]: ...
    async def get(self, tx_id: UUID, user_id: UUID) -> Transaction | None: ...
    async def exists_by_dedup(self, user_id: UUID, dedup_hash: str) -> bool: ...
    async def list_for_portfolio(
        self, portfolio_id: UUID, user_id: UUID
    ) -> list[Transaction]: ...
    async def list_for_asset(
        self, portfolio_id: UUID, asset_id: UUID, user_id: UUID
    ) -> list[Transaction]: ...
    async def soft_delete(self, tx_id: UUID, user_id: UUID) -> None: ...


@runtime_checkable
class PositionRepository(Protocol):
    async def get(self, portfolio_id: UUID, asset_id: UUID) -> Position | None: ...
    async def list_for_portfolio(self, portfolio_id: UUID, user_id: UUID) -> list[Position]: ...
    async def upsert(self, user_id: UUID, position: Position) -> Position: ...
    async def delete(self, portfolio_id: UUID, asset_id: UUID) -> None: ...


@runtime_checkable
class DividendRepository(Protocol):
    async def add(self, user_id: UUID, portfolio_id: UUID, dividend: DividendEvent) -> None: ...
    async def list_for_user(
        self, user_id: UUID, year: int | None = None
    ) -> list[DividendEvent]: ...
    async def list_for_asset(self, user_id: UUID, asset_id: UUID) -> list[DividendEvent]: ...


@runtime_checkable
class FundamentalsRepository(Protocol):
    async def latest(self, asset_id: UUID) -> Fundamentals | None: ...
    async def upsert(self, fundamentals: Fundamentals) -> None: ...


@runtime_checkable
class PriceRepository(Protocol):
    async def latest_price(self, asset_id: UUID) -> tuple[date, "object"] | None: ...
    async def upsert_bars(self, asset_id: UUID, bars: list[tuple]) -> None: ...
