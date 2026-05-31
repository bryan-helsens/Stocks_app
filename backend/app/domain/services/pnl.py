"""Cost-basis and profit/loss engine.

Rebuilds a :class:`Position` from an ordered stream of transactions and computes
**realized** P/L using the configured cost-basis method (FIFO by default, per
business rule BR2). Stock splits adjust the open lots consistently (BR6).

Pure, deterministic and side-effect free — this is the most heavily unit-tested
part of the system. All money maths use :class:`decimal.Decimal`.

Amounts are expressed in the transaction currency converted to the portfolio
base currency via each transaction's ``fx_rate`` (so the engine works in base
currency throughout). The caller is responsible for supplying ``fx_rate``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.domain.entities import Position, Transaction
from app.domain.value_objects.enums import CostBasisMethod, TransactionType


@dataclass(slots=True)
class _Lot:
    """An open purchase lot: *quantity* shares at *unit_cost* (base currency)."""

    quantity: Decimal
    unit_cost: Decimal  # includes allocated buy fees per share


@dataclass(slots=True)
class PnLResult:
    """Outcome of replaying a transaction stream for one asset."""

    position: Position
    realized_pnl: Decimal
    total_dividends: Decimal
    total_fees: Decimal
    total_taxes: Decimal


class InsufficientSharesError(ValueError):
    """Raised when a SELL exceeds the currently held quantity."""


def _base(amount: Decimal, fx_rate: Decimal) -> Decimal:
    """Convert a transaction-currency *amount* to base currency."""
    return amount * fx_rate


def build_position(
    portfolio_id: UUID,
    asset_id: UUID,
    transactions: list[Transaction],
    base_currency: str = "EUR",
    method: CostBasisMethod = CostBasisMethod.FIFO,
) -> PnLResult:
    """Replay *transactions* (for a single asset) into a Position + P/L.

    Transactions are processed in chronological order. Supported types:
    BUY, SELL, DIVIDEND, FEE, TAX, STOCK_SPLIT, REVERSE_SPLIT. DEPOSIT and
    WITHDRAWAL carry no asset and are ignored here (handled at cash level).

    Args:
        transactions: all transactions for one ``asset_id`` (any order).
        method: FIFO (default), LIFO or AVERAGE.

    Returns:
        A :class:`PnLResult` with the resulting open position and realized P/L.
    """
    lots: deque[_Lot] = deque()
    realized = Decimal(0)
    total_dividends = Decimal(0)
    total_fees = Decimal(0)
    total_taxes = Decimal(0)

    ordered = sorted(transactions, key=lambda t: t.trade_date)

    for tx in ordered:
        fx = tx.fx_rate or Decimal(1)
        fee = _base(tx.fee or Decimal(0), fx)
        tax = _base(tx.tax or Decimal(0), fx)
        total_fees += fee
        total_taxes += tax

        if tx.type == TransactionType.BUY:
            qty = tx.quantity or Decimal(0)
            if qty <= 0:
                continue
            gross = _base((tx.price or Decimal(0)) * qty, fx)
            # Buy fees increase cost basis; allocate per share.
            unit_cost = (gross + fee) / qty
            lots.append(_Lot(quantity=qty, unit_cost=unit_cost))

        elif tx.type == TransactionType.SELL:
            qty = tx.quantity or Decimal(0)
            if qty <= 0:
                continue
            held = sum((lot.quantity for lot in lots), Decimal(0))
            if qty > held:
                raise InsufficientSharesError(
                    f"SELL {qty} exceeds held {held} for asset {asset_id}"
                )
            proceeds_per_share = _base(tx.price or Decimal(0), fx)
            # Sell fees/taxes reduce proceeds.
            proceeds = proceeds_per_share * qty - fee - tax
            cost_removed = _consume_lots(lots, qty, method)
            realized += proceeds - cost_removed

        elif tx.type == TransactionType.DIVIDEND:
            # Dividend net of withholding/tax already captured via gross/tax.
            gross = _base(tx.gross_amount or Decimal(0), fx)
            total_dividends += gross - tax

        elif tx.type in (TransactionType.STOCK_SPLIT, TransactionType.REVERSE_SPLIT):
            ratio = tx.split_ratio or Decimal(1)
            if ratio <= 0:
                continue
            _apply_split(lots, ratio)

        elif tx.type in (TransactionType.FEE, TransactionType.TAX):
            # Standalone fee/tax: already accumulated above; no lot effect.
            continue

    quantity = sum((lot.quantity for lot in lots), Decimal(0))
    total_invested = sum((lot.quantity * lot.unit_cost for lot in lots), Decimal(0))
    avg_cost = (total_invested / quantity) if quantity > 0 else Decimal(0)

    position = Position(
        portfolio_id=portfolio_id,
        asset_id=asset_id,
        quantity=quantity,
        avg_cost=avg_cost,
        total_invested=total_invested,
        realized_pnl=realized,
        currency=base_currency,
    )
    return PnLResult(
        position=position,
        realized_pnl=realized,
        total_dividends=total_dividends,
        total_fees=total_fees,
        total_taxes=total_taxes,
    )


def _consume_lots(lots: deque[_Lot], qty: Decimal, method: CostBasisMethod) -> Decimal:
    """Remove *qty* shares from *lots*, returning the cost basis removed."""
    remaining = qty
    cost_removed = Decimal(0)

    if method == CostBasisMethod.AVERAGE:
        total_qty = sum((lot.quantity for lot in lots), Decimal(0))
        total_cost = sum((lot.quantity * lot.unit_cost for lot in lots), Decimal(0))
        avg = total_cost / total_qty if total_qty > 0 else Decimal(0)
        cost_removed = avg * qty
        # Shrink lots proportionally by clearing and re-seeding a single lot.
        new_qty = total_qty - qty
        lots.clear()
        if new_qty > 0:
            lots.append(_Lot(quantity=new_qty, unit_cost=avg))
        return cost_removed

    # FIFO consumes from the left; LIFO from the right.
    pop = lots.popleft if method == CostBasisMethod.FIFO else lots.pop
    push_back = lots.appendleft if method == CostBasisMethod.FIFO else lots.append

    while remaining > 0 and lots:
        lot = pop()
        if lot.quantity <= remaining:
            cost_removed += lot.quantity * lot.unit_cost
            remaining -= lot.quantity
        else:
            cost_removed += remaining * lot.unit_cost
            lot.quantity -= remaining
            remaining = Decimal(0)
            push_back(lot)
    return cost_removed


def _apply_split(lots: deque[_Lot], ratio: Decimal) -> None:
    """Adjust open lots for a split: quantity × ratio, unit cost ÷ ratio.

    A 2:1 forward split uses ratio=2; a 1:10 reverse split uses ratio=Decimal('0.1').
    Total cost basis is preserved.
    """
    for lot in lots:
        lot.quantity = lot.quantity * ratio
        lot.unit_cost = lot.unit_cost / ratio
