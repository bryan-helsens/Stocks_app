"""Dividend dashboard schemas (M5/M6)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class DividendDashboardResponse(BaseModel):
    total_received: Decimal
    by_month: dict[str, Decimal]
    by_year: dict[int, Decimal]
    by_sector: dict[str, Decimal]
    by_country: dict[str, Decimal]
    cagr: Decimal | None
    avg_monthly: Decimal
    projected_next_12m: Decimal
    currency: str
    note: str
