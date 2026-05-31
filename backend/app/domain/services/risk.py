"""Risk metrics: volatility, concentration and a 0–100 portfolio risk score.

Pure statistical helpers used by the dashboard (FR7.4) and the AI context
builder. Educational only.
"""

from __future__ import annotations

import math
from decimal import Decimal

from app.domain.value_objects.money import to_decimal


def returns_from_prices(prices: list[Decimal]) -> list[float]:
    """Compute simple period-over-period returns from a price series."""
    out: list[float] = []
    for prev, cur in zip(prices, prices[1:], strict=False):
        p = float(to_decimal(prev))
        if p == 0:
            continue
        out.append(float(to_decimal(cur)) / p - 1.0)
    return out


def volatility(returns: list[float], annualization: int = 252) -> Decimal:
    """Annualised standard deviation of *returns* (sample stdev)."""
    n = len(returns)
    if n < 2:
        return Decimal(0)
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    return to_decimal(math.sqrt(var) * math.sqrt(annualization))


def concentration_hhi(weights: list[Decimal]) -> Decimal:
    """Herfindahl-Hirschman index of position weights (0–1, higher = concentrated)."""
    return sum((to_decimal(w) ** 2 for w in weights), Decimal(0))


def max_drawdown(values: list[Decimal]) -> Decimal:
    """Maximum peak-to-trough decline of an equity curve, as a fraction (0–1)."""
    peak = None
    mdd = Decimal(0)
    for v in values:
        val = to_decimal(v)
        if peak is None or val > peak:
            peak = val
        if peak and peak > 0:
            dd = (peak - val) / peak
            if dd > mdd:
                mdd = dd
    return mdd


def risk_score(
    annual_volatility: Decimal,
    concentration: Decimal,
    drawdown: Decimal,
) -> Decimal:
    """Blend volatility, concentration and drawdown into a 0–100 risk score.

    Higher score = higher risk. Weights: volatility 40%, concentration 35%,
    drawdown 25%. Each component is scaled to a 0–100 sub-score.
    """
    vol = to_decimal(annual_volatility)
    # ~40% annualised vol maps to ~100.
    vol_sub = min(Decimal(100), vol / Decimal("0.40") * Decimal(100))
    conc_sub = min(Decimal(100), to_decimal(concentration) * Decimal(100))
    dd_sub = min(Decimal(100), to_decimal(drawdown) * Decimal(100))
    score = vol_sub * Decimal("0.40") + conc_sub * Decimal("0.35") + dd_sub * Decimal("0.25")
    return max(Decimal(0), min(Decimal(100), score))
