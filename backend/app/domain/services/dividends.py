"""Dividend analytics (pure functions).

Implements the dividend metrics from FR5.2 / business rules BR4–BR5:
current yield, yield on cost, dividend CAGR, total received, projected future
dividends and a heuristic dividend-safety score.

All outputs are **informational/educational** — projections are estimates, not
guarantees (BR10).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.value_objects.money import to_decimal


def current_yield(annual_dividend_per_share: Decimal, price: Decimal) -> Decimal | None:
    """Forward dividend yield = annual DPS / current price.

    Returns ``None`` when price is non-positive (yield undefined).
    """
    price = to_decimal(price)
    if price <= 0:
        return None
    return to_decimal(annual_dividend_per_share) / price


def yield_on_cost(annual_dividend_per_share: Decimal, avg_cost: Decimal) -> Decimal | None:
    """Yield on cost = annual DPS / average cost basis per share (BR4)."""
    avg_cost = to_decimal(avg_cost)
    if avg_cost <= 0:
        return None
    return to_decimal(annual_dividend_per_share) / avg_cost


def dividend_cagr(history: list[tuple[int, Decimal]]) -> Decimal | None:
    """Compound annual growth rate of dividends over a yearly *history*.

    Args:
        history: list of ``(year, total_dividend_for_year)`` pairs. Order is
            normalised internally.

    Returns:
        CAGR = (last / first) ** (1 / years) - 1, or ``None`` when it cannot be
        computed (fewer than two points, non-positive endpoints).
    """
    points = sorted((y, to_decimal(v)) for y, v in history)
    if len(points) < 2:
        return None
    first = points[0][1]
    last = points[-1][1]
    n_years = points[-1][0] - points[0][0]
    if first <= 0 or last <= 0 or n_years <= 0:
        return None
    # Decimal has no fractional power; use float for the exponent then re-quantise.
    ratio = float(last / first)
    cagr = ratio ** (1.0 / n_years) - 1.0
    return to_decimal(cagr)


def total_received(payments: list[Decimal]) -> Decimal:
    """Sum of all received dividend payments (already net or gross as supplied)."""
    return sum((to_decimal(p) for p in payments), Decimal(0))


def project_future_dividends(
    shares: Decimal,
    last_annual_dps: Decimal,
    growth_rate: Decimal,
    years: int = 1,
) -> list[Decimal]:
    """Project forward annual dividend income (FR5.2 — estimate only).

    Compounds *last_annual_dps* by *growth_rate* each year and multiplies by the
    held *shares*. Returns one figure per projected year.
    """
    shares = to_decimal(shares)
    dps = to_decimal(last_annual_dps)
    g = to_decimal(growth_rate)
    out: list[Decimal] = []
    for _ in range(max(0, years)):
        dps = dps * (Decimal(1) + g)
        out.append(shares * dps)
    return out


@dataclass(slots=True)
class DividendSafety:
    """Heuristic dividend-safety assessment (0–100, higher = safer)."""

    score: Decimal
    label: str
    factors: dict[str, str]


def dividend_safety(
    payout_ratio: Decimal | None,
    fcf_payout_ratio: Decimal | None,
    debt_equity: Decimal | None,
    years_of_growth: int,
    recent_cut: bool,
) -> DividendSafety:
    """Heuristic safety score from coverage, leverage and consistency (FR5.3).

    This is a transparent rule-of-thumb, **not** advice. Each factor nudges a
    baseline of 50 up or down within [0, 100].
    """
    score = Decimal(50)
    factors: dict[str, str] = {}

    if payout_ratio is not None:
        pr = to_decimal(payout_ratio)
        if pr <= Decimal("0.5"):
            score += 15
            factors["payout_ratio"] = "comfortable (<=50%)"
        elif pr <= Decimal("0.75"):
            score += 5
            factors["payout_ratio"] = "moderate (50-75%)"
        elif pr <= Decimal("1.0"):
            score -= 10
            factors["payout_ratio"] = "stretched (75-100%)"
        else:
            score -= 25
            factors["payout_ratio"] = "unsustainable (>100%)"

    if fcf_payout_ratio is not None:
        fpr = to_decimal(fcf_payout_ratio)
        if fpr <= Decimal("0.7"):
            score += 15
            factors["fcf_coverage"] = "well covered by free cash flow"
        elif fpr <= Decimal("1.0"):
            score += 2
            factors["fcf_coverage"] = "covered but tight"
        else:
            score -= 15
            factors["fcf_coverage"] = "not covered by free cash flow"

    if debt_equity is not None:
        de = to_decimal(debt_equity)
        if de <= Decimal("1.0"):
            score += 8
            factors["leverage"] = "low debt"
        elif de <= Decimal("2.0"):
            factors["leverage"] = "moderate debt"
        else:
            score -= 12
            factors["leverage"] = "high debt"

    if years_of_growth >= 10:
        score += 12
        factors["consistency"] = f"{years_of_growth}y of growth"
    elif years_of_growth >= 5:
        score += 6
        factors["consistency"] = f"{years_of_growth}y of growth"

    if recent_cut:
        score -= 30
        factors["recent_cut"] = "dividend was recently cut"

    score = max(Decimal(0), min(Decimal(100), score))
    if score >= 75:
        label = "Safe"
    elif score >= 50:
        label = "Borderline"
    else:
        label = "At risk"
    return DividendSafety(score=score, label=label, factors=factors)
