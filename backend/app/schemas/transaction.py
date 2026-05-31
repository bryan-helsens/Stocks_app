"""Transaction schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.value_objects.enums import TransactionType


class TransactionCreate(BaseModel):
    portfolio_id: UUID
    type: TransactionType
    trade_date: datetime
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    asset_id: UUID | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    gross_amount: Decimal = Decimal(0)
    fee: Decimal = Decimal(0)
    tax: Decimal = Decimal(0)
    fx_rate: Decimal = Decimal(1)
    split_ratio: Decimal | None = None
    external_id: str | None = None
    note: str | None = None
    allow_duplicate: bool = False


class TransactionResponse(BaseModel):
    id: UUID | None
    portfolio_id: UUID
    type: TransactionType
    trade_date: datetime
    currency: str
    asset_id: UUID | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    gross_amount: Decimal
    fee: Decimal
    tax: Decimal
    net_amount: Decimal
    note: str | None = None
