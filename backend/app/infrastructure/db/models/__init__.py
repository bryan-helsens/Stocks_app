"""SQLAlchemy ORM models — a 1:1 mapping of ``db/schema.sql``.

These are persistence models only; business logic lives in the domain layer.
Repositories translate between these models and domain entities. Enum columns
reuse the domain :mod:`app.domain.value_objects.enums` types via SQLAlchemy's
native ``Enum`` (stored as PostgreSQL enum types).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, ENUM, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.value_objects.enums import (
    AIProvider,
    AlertChannel,
    AlertType,
    AssetClass,
    CostBasisMethod,
    DividendKind,
    ImportRowStatus,
    ImportStatus,
    NotificationStatus,
    Recommendation,
    ReportFormat,
    ReportStatus,
    ReportType,
    TransactionSource,
    TransactionType,
    ValuationMethod,
    ValuationVerdict,
)
from app.infrastructure.db.base import Base

# Money / rate column helpers --------------------------------------------------
Money = Numeric(20, 8)
Rate = Numeric(20, 8)


def _pk() -> Mapped[uuid.UUID]:
    # server_default matches db/schema.sql (gen_random_uuid()) so raw SQL inserts
    # also get a PK; the Python-side default keeps ORM round-trips populated.
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


def _ts_created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _ts_updated() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def _enum(py_enum: type, name: str) -> ENUM:
    """Native PostgreSQL enum bound to a Python StrEnum (created by migrations)."""
    return ENUM(
        py_enum,
        name=name,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


# ===========================================================================
# Identity & security
# ===========================================================================
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text)
    base_currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    locale: Mapped[str] = mapped_column(Text, default="nl-BE", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(Text)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = _ts_created()
    updated_at: Mapped[datetime] = _ts_updated()

    settings: Mapped[UserSettings | None] = relationship(back_populates="user", uselist=False)
    portfolios: Mapped[list[Portfolio]] = relationship(back_populates="user")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_name: Mapped[str | None] = mapped_column(Text)
    platform: Mapped[str | None] = mapped_column(Text)
    push_token: Mapped[str | None] = mapped_column(Text)
    refresh_token_hash: Mapped[str | None] = mapped_column(Text)
    biometric_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts_created()


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    theme: Mapped[str] = mapped_column(Text, default="system", nullable=False)
    cost_basis_method: Mapped[CostBasisMethod] = mapped_column(
        _enum(CostBasisMethod, "cost_basis_method"), default=CostBasisMethod.FIFO, nullable=False
    )
    dividend_tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.30"))
    fire_annual_expenses: Mapped[Decimal | None] = mapped_column(Money)
    fire_swr: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.04"))
    ai_provider: Mapped[AIProvider] = mapped_column(
        _enum(AIProvider, "ai_provider"), default=AIProvider.OLLAMA, nullable=False
    )
    notify_quiet_hours: Mapped[dict] = mapped_column(JSONB, default=dict)
    provider_keys: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = _ts_updated()

    user: Mapped[User] = relationship(back_populates="settings")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(INET)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _ts_created()


# ===========================================================================
# Reference data
# ===========================================================================
class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("ticker", "exchange", name="ux_assets_ticker_exchange"),)

    id: Mapped[uuid.UUID] = _pk()
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    isin: Mapped[str | None] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    asset_class: Mapped[AssetClass] = mapped_column(_enum(AssetClass, "asset_class"), nullable=False)
    sector: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(2))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    exchange: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = _ts_created()
    updated_at: Mapped[datetime] = _ts_updated()


class PriceHistory(Base):
    __tablename__ = "price_history"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[Decimal | None] = mapped_column(Money)
    high: Mapped[Decimal | None] = mapped_column(Money)
    low: Mapped[Decimal | None] = mapped_column(Money)
    close: Mapped[Decimal] = mapped_column(Money, nullable=False)
    volume: Mapped[int | None] = mapped_column(BigInteger)


class FxRate(Base):
    __tablename__ = "fx_rates"

    base: Mapped[str] = mapped_column(String(3), primary_key=True)
    quote: Mapped[str] = mapped_column(String(3), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    rate: Mapped[Decimal] = mapped_column(Rate, nullable=False)


class Fundamentals(Base):
    __tablename__ = "fundamentals"
    __table_args__ = (UniqueConstraint("asset_id", "as_of", "source"),)

    id: Mapped[uuid.UUID] = _pk()
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    pe: Mapped[Decimal | None] = mapped_column(Money)
    forward_pe: Mapped[Decimal | None] = mapped_column(Money)
    peg: Mapped[Decimal | None] = mapped_column(Money)
    roe: Mapped[Decimal | None] = mapped_column(Money)
    roic: Mapped[Decimal | None] = mapped_column(Money)
    debt_equity: Mapped[Decimal | None] = mapped_column(Money)
    fcf: Mapped[Decimal | None] = mapped_column(Money)
    payout_ratio: Mapped[Decimal | None] = mapped_column(Money)
    revenue_growth: Mapped[Decimal | None] = mapped_column(Money)
    earnings_growth: Mapped[Decimal | None] = mapped_column(Money)
    dividend_growth: Mapped[Decimal | None] = mapped_column(Money)
    eps: Mapped[Decimal | None] = mapped_column(Money)
    book_value: Mapped[Decimal | None] = mapped_column(Money)
    raw: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts_created()


class DividendSchedule(Base):
    __tablename__ = "dividend_schedule"

    id: Mapped[uuid.UUID] = _pk()
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    ex_date: Mapped[date | None] = mapped_column(Date, index=True)
    record_date: Mapped[date | None] = mapped_column(Date)
    pay_date: Mapped[date | None] = mapped_column(Date, index=True)
    amount_per_share: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    frequency: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[DividendKind] = mapped_column(
        _enum(DividendKind, "dividend_kind"), default=DividendKind.CONFIRMED, nullable=False
    )
    source: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts_created()


# ===========================================================================
# Portfolio & transactions
# ===========================================================================
class Broker(Base):
    __tablename__ = "brokers"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    country: Mapped[str | None] = mapped_column(String(2))
    default_currency: Mapped[str | None] = mapped_column(String(3))
    parser_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts_created()


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    base_currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = _ts_created()
    updated_at: Mapped[datetime] = _ts_updated()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="portfolios")


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    broker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brokers.id", ondelete="SET NULL"))
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portfolios.id", ondelete="SET NULL")
    )
    filename: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    file_type: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ImportStatus] = mapped_column(
        _enum(ImportStatus, "import_status"), default=ImportStatus.PENDING, nullable=False
    )
    detected_columns: Mapped[dict | None] = mapped_column(JSONB)
    column_mapping: Mapped[dict | None] = mapped_column(JSONB)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dup_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts_created()
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("user_id", "dedup_hash", name="ux_tx_dedup"),
        CheckConstraint(
            "type NOT IN ('BUY','SELL','DIVIDEND','STOCK_SPLIT','REVERSE_SPLIT') "
            "OR asset_id IS NOT NULL",
            name="ck_tx_trade_requires_asset",
        ),
        CheckConstraint(
            "type NOT IN ('BUY','SELL') OR (quantity IS NOT NULL AND price IS NOT NULL)",
            name="ck_tx_trade_requires_qty",
        ),
        CheckConstraint(
            "type NOT IN ('STOCK_SPLIT','REVERSE_SPLIT') OR split_ratio IS NOT NULL",
            name="ck_tx_split_ratio",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="RESTRICT"), nullable=False
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"))
    broker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brokers.id", ondelete="SET NULL"))
    type: Mapped[TransactionType] = mapped_column(
        _enum(TransactionType, "transaction_type"), nullable=False
    )
    trade_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settle_date: Mapped[date | None] = mapped_column(Date)
    quantity: Mapped[Decimal | None] = mapped_column(Money)
    price: Mapped[Decimal | None] = mapped_column(Money)
    gross_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    tax: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    fx_rate: Mapped[Decimal] = mapped_column(Rate, default=Decimal(1), nullable=False)
    split_ratio: Mapped[Decimal | None] = mapped_column(Rate)
    source: Mapped[TransactionSource] = mapped_column(
        _enum(TransactionSource, "transaction_source"),
        default=TransactionSource.MANUAL,
        nullable=False,
    )
    external_id: Mapped[str | None] = mapped_column(Text)
    dedup_hash: Mapped[str] = mapped_column(Text, nullable=False)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts_created()
    updated_at: Mapped[datetime] = _ts_updated()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportRow(Base):
    __tablename__ = "import_rows"

    id: Mapped[uuid.UUID] = _pk()
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    normalized: Mapped[dict | None] = mapped_column(JSONB)
    suggested_type: Mapped[TransactionType | None] = mapped_column(
        _enum(TransactionType, "transaction_type")
    )
    status: Mapped[ImportRowStatus] = mapped_column(
        _enum(ImportRowStatus, "import_row_status"), default=ImportRowStatus.NEW, nullable=False
    )
    dedup_hash: Mapped[str | None] = mapped_column(Text)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )
    error: Mapped[str | None] = mapped_column(Text)


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("portfolio_id", "asset_id", name="ux_position_pa"),)

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="RESTRICT"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    avg_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    total_invested: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = _ts_updated()


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    total_value: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    day_change: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)


# ===========================================================================
# Dividends, analysis, AI
# ===========================================================================
class Dividend(Base):
    __tablename__ = "dividends"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="RESTRICT"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )
    ex_date: Mapped[date | None] = mapped_column(Date)
    pay_date: Mapped[date | None] = mapped_column(Date)
    amount_per_share: Mapped[Decimal | None] = mapped_column(Money)
    shares: Mapped[Decimal | None] = mapped_column(Money)
    gross_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    withholding_tax: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    belgian_rv: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    source_country: Mapped[str | None] = mapped_column(String(2))
    created_at: Mapped[datetime] = _ts_created()


class AssetScore(Base):
    __tablename__ = "asset_scores"
    __table_args__ = (UniqueConstraint("asset_id", "as_of"),)

    id: Mapped[uuid.UUID] = _pk()
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    valuation_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    growth_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    health_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    dividend_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    breakdown: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _ts_created()


class Valuation(Base):
    __tablename__ = "valuations"

    id: Mapped[uuid.UUID] = _pk()
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    method: Mapped[ValuationMethod] = mapped_column(
        _enum(ValuationMethod, "valuation_method"), nullable=False
    )
    fair_value: Mapped[Decimal | None] = mapped_column(Money)
    current_price: Mapped[Decimal | None] = mapped_column(Money)
    margin_of_safety: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    verdict: Mapped[ValuationVerdict | None] = mapped_column(
        _enum(ValuationVerdict, "valuation_verdict")
    )
    assumptions: Mapped[dict | None] = mapped_column(JSONB)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = _ts_created()


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE")
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    provider: Mapped[AIProvider] = mapped_column(_enum(AIProvider, "ai_provider"), nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[Recommendation | None] = mapped_column(
        _enum(Recommendation, "recommendation")
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    strengths: Mapped[dict | None] = mapped_column(JSONB)
    weaknesses: Mapped[dict | None] = mapped_column(JSONB)
    opportunities: Mapped[dict | None] = mapped_column(JSONB)
    threats: Mapped[dict | None] = mapped_column(JSONB)
    summary: Mapped[str | None] = mapped_column(Text)
    context_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    raw_response: Mapped[dict | None] = mapped_column(JSONB)
    disclaimer: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _ts_created()


# ===========================================================================
# FIRE, scenarios, watchlist, alerts, notifications, tax, reports
# ===========================================================================
class FirePlan(Base):
    __tablename__ = "fire_plans"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    annual_expenses: Mapped[Decimal] = mapped_column(Money, nullable=False)
    swr: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.04"), nullable=False)
    expected_return: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.07"))
    expected_dividend_growth: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.05"))
    monthly_contribution: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    inflation: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.02"))
    targets: Mapped[dict | None] = mapped_column(JSONB)
    fi_date: Mapped[date | None] = mapped_column(Date)
    projection: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _ts_created()
    updated_at: Mapped[datetime] = _ts_updated()


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fire_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fire_plans.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _ts_created()


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _ts_created()


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "asset_id"),)

    id: Mapped[uuid.UUID] = _pk()
    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    target_price: Mapped[Decimal | None] = mapped_column(Money)
    fair_value_alert: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dividend_alert: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts_created()


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE")
    )
    type: Mapped[AlertType] = mapped_column(_enum(AlertType, "alert_type"), nullable=False)
    threshold: Mapped[dict | None] = mapped_column(JSONB)
    channels: Mapped[list[str]] = mapped_column(
        ARRAY(_enum(AlertChannel, "alert_channel")), default=list
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts_created()


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("alerts.id", ondelete="SET NULL"))
    type: Mapped[AlertType] = mapped_column(_enum(AlertType, "alert_type"), nullable=False)
    channel: Mapped[AlertChannel] = mapped_column(_enum(AlertChannel, "alert_channel"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[NotificationStatus] = mapped_column(
        _enum(NotificationStatus, "notification_status"),
        default=NotificationStatus.PENDING,
        nullable=False,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts_created()


class TaxSummary(Base):
    __tablename__ = "tax_summaries"
    __table_args__ = (UniqueConstraint("user_id", "year"),)

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    foreign_dividends_gross: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    belgian_dividends_gross: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    withholding_tax_foreign: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    belgian_rv: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    tob_total: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    fees_total: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    net_dividend_income: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    breakdown: Mapped[dict | None] = mapped_column(JSONB)
    generated_at: Mapped[datetime] = _ts_created()


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[ReportType] = mapped_column(_enum(ReportType, "report_type"), nullable=False)
    format: Mapped[ReportFormat] = mapped_column(_enum(ReportFormat, "report_format"), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        _enum(ReportStatus, "report_status"), default=ReportStatus.QUEUED, nullable=False
    )
    params: Mapped[dict | None] = mapped_column(JSONB)
    file_path: Mapped[str | None] = mapped_column(Text)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts_created()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


__all__ = [
    "User", "Device", "UserSettings", "AuditLog",
    "Asset", "PriceHistory", "FxRate", "Fundamentals", "DividendSchedule",
    "Broker", "Portfolio", "ImportBatch", "Transaction", "ImportRow",
    "Position", "PortfolioSnapshot", "Dividend",
    "AssetScore", "Valuation", "AIAnalysis",
    "FirePlan", "Scenario", "Watchlist", "WatchlistItem",
    "Alert", "Notification", "TaxSummary", "Report",
]
