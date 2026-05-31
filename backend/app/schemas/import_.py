"""Import schemas (M4)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class ImportRowPreview(BaseModel):
    type: str | None
    trade_date: str
    ticker: str | None = None
    isin: str | None = None
    quantity: str | None = None
    price: str | None = None
    gross_amount: str | None = None
    fee: str
    tax: str
    currency: str
    status: str
    error: str | None = None


class ImportPreviewResponse(BaseModel):
    batch_id: UUID
    status: str
    row_count: int
    new_count: int
    dup_count: int
    invalid_count: int
    column_mapping: dict
    rows: list[ImportRowPreview]


class ImportCommitResponse(BaseModel):
    committed: int
    message: str
