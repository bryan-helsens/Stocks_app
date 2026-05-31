"""Domain entities — pure dataclasses with no I/O or framework dependencies.

Entities model the business concepts (assets, transactions, positions, …) and
are the currency passed between the domain services and the application layer.
Persistence concerns (SQLAlchemy) live entirely in ``infrastructure.db``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.domain.value_objects.enums import (
    AssetClass,
    DividendKind,
    Recommendation,
    TransactionSource,
    TransactionType,
    ValuationMethod,
    ValuationVerdict,
)


@dataclass(slots=True)
class Asset:
    """A tradeable instrument shared across users."""

    id: UUID | None
    ticker: str
    name: str
    asset_class: AssetClass
    isin: str | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    currency: str = "USD"
    exchange: str | None = None


@dataclass(slots=True)
class Transaction:
    """A single ledger entry — the single source of truth for positions."""

    id: UUID | None
    user_id: UUID
    portfolio_id: UUID
    type: TransactionType
    trade_date: datetime
    currency: str
    asset_id: UUID | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    gross_amount: Decimal = Decimal(0)
    fee: Decimal = Decimal(0)
    tax: Decimal = Decimal(0)
    net_amount: Decimal = Decimal(0)
    fx_rate: Decimal = Decimal(1)
    split_ratio: Decimal | None = None
    source: TransactionSource = TransactionSource.MANUAL
    external_id: str | None = None
    note: str | None = None


@dataclass(slots=True)
class Position:
    """Aggregated holding for one asset within one portfolio (derived)."""

    portfolio_id: UUID
    asset_id: UUID
    quantity: Decimal = Decimal(0)
    avg_cost: Decimal = Decimal(0)
    total_invested: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)
    currency: str = "EUR"

    @property
    def is_open(self) -> bool:
        return self.quantity > 0

    def market_value(self, price: Decimal) -> Decimal:
        return self.quantity * price

    def unrealized_pnl(self, price: Decimal) -> Decimal:
        return self.market_value(price) - self.total_invested


@dataclass(slots=True)
class DividendEvent:
    """A received (or projected) dividend payment."""

    asset_id: UUID
    ex_date: date | None
    pay_date: date | None
    amount_per_share: Decimal
    shares: Decimal
    gross_amount: Decimal
    currency: str
    withholding_tax: Decimal = Decimal(0)
    belgian_rv: Decimal = Decimal(0)
    net_amount: Decimal = Decimal(0)
    source_country: str | None = None
    kind: DividendKind = DividendKind.CONFIRMED


@dataclass(slots=True)
class Fundamentals:
    """A point-in-time snapshot of company fundamentals/ratios."""

    asset_id: UUID
    as_of: date
    pe: Decimal | None = None
    forward_pe: Decimal | None = None
    peg: Decimal | None = None
    roe: Decimal | None = None
    roic: Decimal | None = None
    debt_equity: Decimal | None = None
    fcf: Decimal | None = None
    payout_ratio: Decimal | None = None
    revenue_growth: Decimal | None = None
    earnings_growth: Decimal | None = None
    dividend_growth: Decimal | None = None
    eps: Decimal | None = None
    book_value: Decimal | None = None


@dataclass(slots=True)
class Valuation:
    """Output of a valuation model."""

    method: ValuationMethod
    fair_value: Decimal | None
    current_price: Decimal | None
    margin_of_safety: Decimal | None
    verdict: ValuationVerdict
    assumptions: dict = field(default_factory=dict)


@dataclass(slots=True)
class AssetScore:
    """0–100 quality score with weighted sub-scores (educational)."""

    total: Decimal
    valuation: Decimal
    growth: Decimal
    health: Decimal
    dividend: Decimal
    breakdown: dict = field(default_factory=dict)


@dataclass(slots=True)
class SignalReport:
    """Buy/Hold/Sell signal with confidence and SWOT (informational only)."""

    label: Recommendation
    confidence: Decimal
    risk_score: Decimal
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)
    threats: list[str] = field(default_factory=list)
