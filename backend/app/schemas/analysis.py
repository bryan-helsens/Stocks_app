"""Analysis & valuation schemas (M8/M9)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from app.domain.value_objects.enums import ValuationMethod, ValuationVerdict
from app.schemas.common import DISCLAIMER_NL


class ScoreResponse(BaseModel):
    ticker: str
    has_fundamentals: bool
    total: Decimal | None = None
    valuation: Decimal | None = None
    growth: Decimal | None = None
    health: Decimal | None = None
    dividend: Decimal | None = None
    breakdown: dict | None = None
    disclaimer: str = DISCLAIMER_NL


class ValuationRequest(BaseModel):
    current_price: Decimal | None = None
    # DCF
    free_cash_flow: Decimal | None = None
    shares_outstanding: Decimal | None = None
    growth_rate: Decimal = Decimal("0.08")
    discount_rate: Decimal = Decimal("0.10")
    terminal_growth: Decimal = Decimal("0.025")
    years: int = 10
    # DDM
    dividend_per_share: Decimal | None = None
    dividend_growth: Decimal = Decimal("0.05")
    required_return: Decimal = Decimal("0.09")
    # Multiples
    eps: Decimal | None = None
    peer_pe: Decimal | None = None


class ValuationItem(BaseModel):
    method: ValuationMethod
    fair_value: Decimal | None
    current_price: Decimal | None
    margin_of_safety: Decimal | None
    verdict: ValuationVerdict
    assumptions: dict


class ValuationResponse(BaseModel):
    items: list[ValuationItem]
    disclaimer: str = DISCLAIMER_NL
