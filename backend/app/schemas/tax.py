"""Belgian tax schemas (M17) — informational only."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class TaxLineResponse(BaseModel):
    asset: str
    source_country: str | None
    gross: Decimal
    foreign_withholding: Decimal
    belgian_rv: Decimal
    net: Decimal
    is_foreign: bool


class TaxSummaryResponse(BaseModel):
    year: int
    foreign_dividends_gross: Decimal
    belgian_dividends_gross: Decimal
    withholding_tax_foreign: Decimal
    belgian_rv: Decimal
    tob_total: Decimal
    fees_total: Decimal
    net_dividend_income: Decimal
    reclaimable_exemption: Decimal
    lines: list[TaxLineResponse]
    disclaimer: str
