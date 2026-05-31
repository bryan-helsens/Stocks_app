"""Transaction application service.

Adds/removes transactions and keeps the derived :class:`Position` projection in
sync by replaying the asset's transaction stream through the FIFO P/L engine
(BR1, BR2). Enforces duplicate detection (BR7) and ownership (BR11).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.domain.entities import Transaction
from app.domain.services import pnl
from app.domain.services.pnl import InsufficientSharesError
from app.domain.value_objects.enums import CostBasisMethod, TransactionType
from app.infrastructure.db.repositories import (
    SqlPositionRepository,
    SqlTransactionRepository,
    compute_dedup_hash,
)
from app.infrastructure.db.repositories.users import SqlPortfolioRepository


class TransactionService:
    def __init__(
        self,
        transactions: SqlTransactionRepository,
        positions: SqlPositionRepository,
        portfolios: SqlPortfolioRepository,
    ) -> None:
        self._tx = transactions
        self._pos = positions
        self._portfolios = portfolios

    async def add_transaction(
        self,
        tx: Transaction,
        *,
        cost_basis: CostBasisMethod = CostBasisMethod.FIFO,
        allow_duplicate: bool = False,
    ) -> Transaction:
        """Persist a transaction and rebuild the affected position.

        Raises:
            NotFoundError: the portfolio does not belong to the user.
            ConflictError: a duplicate (same dedup hash) already exists.
            ValidationError: the transaction would create a negative position.
        """
        portfolio = await self._portfolios.get(tx.portfolio_id, tx.user_id)
        if portfolio is None:
            raise NotFoundError("Portfolio not found.")

        self._validate(tx)

        dedup = compute_dedup_hash(tx)
        if not allow_duplicate and await self._tx.exists_by_dedup(tx.user_id, dedup):
            raise ConflictError(
                "This transaction appears to already exist.", details={"dedup": dedup},
            )

        # Compute net amount if not provided.
        if tx.net_amount == 0 and tx.gross_amount:
            sign = Decimal(-1) if tx.type == TransactionType.BUY else Decimal(1)
            tx.net_amount = tx.gross_amount * sign - tx.fee - tx.tax

        saved = await self._tx.add(tx, dedup_hash=dedup)

        if tx.asset_id is not None:
            await self._rebuild_position(
                tx.portfolio_id, tx.asset_id, tx.user_id, portfolio.base_currency, cost_basis
            )
        return saved

    async def delete_transaction(self, tx_id: UUID, user_id: UUID) -> None:
        tx = await self._tx.get(tx_id, user_id)
        if tx is None:
            raise NotFoundError("Transaction not found.")
        await self._tx.soft_delete(tx_id, user_id)
        if tx.asset_id is not None:
            portfolio = await self._portfolios.get(tx.portfolio_id, user_id)
            base = portfolio.base_currency if portfolio else "EUR"
            await self._rebuild_position(tx.portfolio_id, tx.asset_id, user_id, base)

    async def _rebuild_position(
        self,
        portfolio_id: UUID,
        asset_id: UUID,
        user_id: UUID,
        base_currency: str,
        cost_basis: CostBasisMethod = CostBasisMethod.FIFO,
    ) -> None:
        txs = await self._tx.list_for_asset(portfolio_id, asset_id, user_id)
        try:
            result = pnl.build_position(
                portfolio_id, asset_id, txs, base_currency=base_currency, method=cost_basis
            )
        except InsufficientSharesError as exc:
            raise ValidationError(str(exc)) from exc

        if result.position.quantity <= 0 and result.position.realized_pnl == 0:
            await self._pos.delete(portfolio_id, asset_id)
        else:
            await self._pos.upsert(user_id, result.position)

    @staticmethod
    def _validate(tx: Transaction) -> None:
        if tx.type in (TransactionType.BUY, TransactionType.SELL):
            if tx.asset_id is None:
                raise ValidationError(f"{tx.type} requires an asset.")
            if tx.quantity is None or tx.quantity <= 0:
                raise ValidationError(f"{tx.type} requires a positive quantity.")
            if tx.price is None or tx.price < 0:
                raise ValidationError(f"{tx.type} requires a non-negative price.")
        if tx.type in (TransactionType.STOCK_SPLIT, TransactionType.REVERSE_SPLIT) and (
            tx.split_ratio is None or tx.split_ratio <= 0
        ):
            raise ValidationError("Split requires a positive ratio.")
