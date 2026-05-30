"""Scenario simulations for the planner (M11).

Deterministic "what-if" projections plus an optional Monte-Carlo band. As with
FIRE, these are illustrative estimates, never guarantees (BR10). The planner
composes these with :mod:`app.domain.services.fire`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.value_objects.money import to_decimal


@dataclass(slots=True)
class ScenarioResult:
    """Result of a single deterministic scenario."""

    name: str
    final_value: Decimal
    yearly: list[dict] = field(default_factory=list)
    params: dict = field(default_factory=dict)


def simulate(
    initial_value: Decimal,
    monthly_contribution: Decimal,
    annual_return: Decimal,
    years: int,
    *,
    name: str = "base",
    one_off_crash_pct: Decimal | None = None,
    crash_year: int | None = None,
    inflation: Decimal | None = None,
    extra_monthly: Decimal | None = None,
    dividend_change_pct: Decimal | None = None,
    annual_dividend: Decimal | None = None,
) -> ScenarioResult:
    """Run a deterministic projection with optional shocks.

    Args:
        one_off_crash_pct: e.g. Decimal('0.30') applies a -30% drop in *crash_year*.
        inflation: if set, the final value is also reported in real terms.
        extra_monthly: additional monthly contribution (e.g. raised savings rate).
        dividend_change_pct: adjusts *annual_dividend* (e.g. -0.20 for a cut),
            with the (reduced) dividend reinvested annually.

    Returns:
        A :class:`ScenarioResult` with a yearly value trace.
    """
    value = to_decimal(initial_value)
    contrib = to_decimal(monthly_contribution) + to_decimal(extra_monthly or 0)
    monthly_rate = to_decimal(annual_return) / Decimal(12)
    dividend = to_decimal(annual_dividend or 0)
    if dividend_change_pct is not None:
        dividend = dividend * (Decimal(1) + to_decimal(dividend_change_pct))

    yearly: list[dict] = [{"year": 0, "value": value}]
    for year in range(1, max(0, years) + 1):
        for _ in range(12):
            value = value * (Decimal(1) + monthly_rate) + contrib
        # Reinvest annual dividend income.
        value += dividend
        if crash_year is not None and one_off_crash_pct is not None and year == crash_year:
            value = value * (Decimal(1) - to_decimal(one_off_crash_pct))
        yearly.append({"year": year, "value": value})

    result_params: dict = {"annual_return": str(annual_return), "years": years}
    if inflation is not None:
        real = value / ((Decimal(1) + to_decimal(inflation)) ** max(0, years))
        result_params["real_value"] = str(real)
        result_params["inflation"] = str(inflation)

    return ScenarioResult(name=name, final_value=value, yearly=yearly, params=result_params)


@dataclass(slots=True)
class MonteCarloBand:
    """Percentile band (P10/P50/P90) of terminal portfolio value."""

    p10: Decimal
    p50: Decimal
    p90: Decimal
    runs: int


def monte_carlo(
    initial_value: Decimal,
    monthly_contribution: Decimal,
    mean_annual_return: Decimal,
    annual_volatility: Decimal,
    years: int,
    runs: int = 1000,
    seed: int | None = 42,
) -> MonteCarloBand:
    """Estimate a P10/P50/P90 band via Monte-Carlo (illustrative only).

    Each run samples annual returns from a normal distribution
    ``N(mean, volatility)``. Uses floats internally for speed and converts the
    summary percentiles back to Decimal.
    """
    rng = random.Random(seed)
    v0 = float(to_decimal(initial_value))
    contrib = float(to_decimal(monthly_contribution))
    mu = float(to_decimal(mean_annual_return))
    sigma = float(to_decimal(annual_volatility))

    finals: list[float] = []
    for _ in range(max(1, runs)):
        value = v0
        for _y in range(max(0, years)):
            annual = rng.gauss(mu, sigma)
            monthly = annual / 12.0
            for _m in range(12):
                value = value * (1.0 + monthly) + contrib
        finals.append(value)

    finals.sort()
    n = len(finals)

    def pct(p: float) -> Decimal:
        idx = min(n - 1, max(0, int(round(p * (n - 1)))))
        return to_decimal(finals[idx])

    return MonteCarloBand(p10=pct(0.10), p50=pct(0.50), p90=pct(0.90), runs=n)
