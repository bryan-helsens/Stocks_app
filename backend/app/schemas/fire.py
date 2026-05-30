"""FIRE & scenario schemas (M10/M11)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import DISCLAIMER_NL


class FirePlanRequest(BaseModel):
    annual_expenses: Decimal = Field(gt=0)
    swr: Decimal = Field(default=Decimal("0.04"), gt=0, le=1)
    current_value: Decimal = Field(default=Decimal(0), ge=0)
    monthly_contribution: Decimal = Field(default=Decimal(0), ge=0)
    expected_return: Decimal = Field(default=Decimal("0.07"))


class FireTargetsResponse(BaseModel):
    full_number: Decimal
    lean: Decimal
    coast: Decimal
    barista: Decimal
    fat: Decimal


class FirePlanResponse(BaseModel):
    targets: FireTargetsResponse
    fi_date: date | None
    years_to_fi: Decimal | None
    projection: list[dict]
    inputs: dict
    disclaimer: str = DISCLAIMER_NL


class ScenarioRequest(BaseModel):
    name: str = "scenario"
    initial_value: Decimal = Field(ge=0)
    monthly_contribution: Decimal = Field(default=Decimal(0), ge=0)
    annual_return: Decimal = Decimal("0.07")
    years: int = Field(default=20, ge=1, le=80)
    crash_pct: Decimal | None = None
    crash_year: int | None = None
    inflation: Decimal | None = None
    extra_monthly: Decimal | None = None
    dividend_change_pct: Decimal | None = None
    annual_dividend: Decimal | None = None


class ScenarioResponse(BaseModel):
    name: str
    final_value: Decimal
    yearly: list[dict]
    params: dict
    disclaimer: str = DISCLAIMER_NL


class MonteCarloRequest(BaseModel):
    initial_value: Decimal = Field(ge=0)
    monthly_contribution: Decimal = Field(default=Decimal(0), ge=0)
    mean_return: Decimal = Decimal("0.07")
    volatility: Decimal = Decimal("0.15")
    years: int = Field(default=20, ge=1, le=80)
    runs: int = Field(default=1000, ge=100, le=10000)


class MonteCarloResponse(BaseModel):
    p10: Decimal
    p50: Decimal
    p90: Decimal
    runs: int
    disclaimer: str = DISCLAIMER_NL
