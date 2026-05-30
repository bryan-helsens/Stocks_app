"""Quality scoring (M8) and portfolio health score (M14).

Produces transparent 0–100 scores from fundamentals and portfolio composition.
Missing inputs are handled explicitly (sub-score marked "n/a" and down-weighted,
never silently treated as zero — FR8.3). All scores are educational.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.entities import AssetScore, Fundamentals
from app.domain.value_objects.money import to_decimal


def _clamp(value: Decimal) -> Decimal:
    return max(Decimal(0), min(Decimal(100), value))


def _band(value: Decimal | None, thresholds: list[tuple[Decimal, Decimal]]) -> Decimal | None:
    """Map *value* to a score via ascending *thresholds* of (limit, score).

    Returns ``None`` when *value* is ``None`` (unknown), so callers can exclude
    it from the weighted average rather than scoring it 0.
    """
    if value is None:
        return None
    v = to_decimal(value)
    for limit, score in thresholds:
        if v <= limit:
            return score
    return thresholds[-1][1]


def score_asset(f: Fundamentals) -> AssetScore:
    """Compute a 0–100 quality score with four weighted sub-scores.

    Sub-scores: valuation (P/E, PEG), growth (revenue/earnings/dividend growth),
    health (ROE, ROIC, debt/equity, FCF) and dividend (payout ratio). Only
    sub-scores with available data contribute to the total.
    """
    valuation = _score_valuation(f)
    growth = _score_growth(f)
    health = _score_health(f)
    dividend = _score_dividend(f)

    weights = {
        "valuation": (valuation, Decimal("0.30")),
        "growth": (growth, Decimal("0.25")),
        "health": (health, Decimal("0.30")),
        "dividend": (dividend, Decimal("0.15")),
    }
    weighted_sum = Decimal(0)
    weight_total = Decimal(0)
    breakdown: dict[str, str] = {}
    for name, (sub, w) in weights.items():
        if sub is None:
            breakdown[name] = "n/a"
            continue
        breakdown[name] = str(sub)
        weighted_sum += sub * w
        weight_total += w

    total = (weighted_sum / weight_total) if weight_total > 0 else Decimal(0)
    return AssetScore(
        total=_clamp(total),
        valuation=valuation or Decimal(0),
        growth=growth or Decimal(0),
        health=health or Decimal(0),
        dividend=dividend or Decimal(0),
        breakdown=breakdown,
    )


def _score_valuation(f: Fundamentals) -> Decimal | None:
    pe = _band(
        f.pe,
        [(Decimal(10), Decimal(95)), (Decimal(15), Decimal(85)),
         (Decimal(20), Decimal(70)), (Decimal(30), Decimal(50)),
         (Decimal(40), Decimal(30)), (Decimal(10_000), Decimal(15))],
    )
    peg = _band(
        f.peg,
        [(Decimal(1), Decimal(90)), (Decimal("1.5"), Decimal(70)),
         (Decimal(2), Decimal(50)), (Decimal(3), Decimal(30)),
         (Decimal(10_000), Decimal(15))],
    )
    return _avg([pe, peg])


def _score_growth(f: Fundamentals) -> Decimal | None:
    def growth_band(v: Decimal | None) -> Decimal | None:
        if v is None:
            return None
        x = to_decimal(v)
        if x <= 0:
            return Decimal(20)
        if x < Decimal("0.05"):
            return Decimal(45)
        if x < Decimal("0.10"):
            return Decimal(65)
        if x < Decimal("0.20"):
            return Decimal(85)
        return Decimal(95)

    return _avg([
        growth_band(f.revenue_growth),
        growth_band(f.earnings_growth),
        growth_band(f.dividend_growth),
    ])


def _score_health(f: Fundamentals) -> Decimal | None:
    roe = _band(
        _neg_to_zero(f.roe),
        [(Decimal("0.05"), Decimal(40)), (Decimal("0.10"), Decimal(60)),
         (Decimal("0.20"), Decimal(85)), (Decimal(10_000), Decimal(95))],
    )
    roic = _band(
        _neg_to_zero(f.roic),
        [(Decimal("0.05"), Decimal(40)), (Decimal("0.10"), Decimal(65)),
         (Decimal("0.15"), Decimal(85)), (Decimal(10_000), Decimal(95))],
    )
    # Lower debt/equity is better — invert by banding.
    de = None
    if f.debt_equity is not None:
        d = to_decimal(f.debt_equity)
        de = (Decimal(90) if d <= 1 else
              Decimal(70) if d <= 2 else
              Decimal(45) if d <= 3 else Decimal(20))
    fcf = None if f.fcf is None else (Decimal(80) if to_decimal(f.fcf) > 0 else Decimal(25))
    return _avg([roe, roic, de, fcf])


def _score_dividend(f: Fundamentals) -> Decimal | None:
    if f.payout_ratio is None:
        return None
    pr = to_decimal(f.payout_ratio)
    if pr <= 0:
        return Decimal(40)  # no dividend — neutral for this sub-score
    if pr <= Decimal("0.4"):
        return Decimal(90)
    if pr <= Decimal("0.6"):
        return Decimal(80)
    if pr <= Decimal("0.8"):
        return Decimal(60)
    if pr <= Decimal("1.0"):
        return Decimal(35)
    return Decimal(15)


def _neg_to_zero(v: Decimal | None) -> Decimal | None:
    if v is None:
        return None
    d = to_decimal(v)
    return d if d >= 0 else Decimal(0)


def _avg(values: list[Decimal | None]) -> Decimal | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present, Decimal(0)) / Decimal(len(present))


# --------------------------------------------------------------------------- #
# Portfolio health score (M14)
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class HealthScore:
    """0–100 portfolio health score with improvement suggestions."""

    total: Decimal
    components: dict[str, Decimal] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)


def portfolio_health(
    weights_by_asset: dict[str, Decimal],
    weights_by_sector: dict[str, Decimal],
    weights_by_country: dict[str, Decimal],
    cash_weight: Decimal,
    avg_dividend_safety: Decimal | None,
    risk_score: Decimal,
) -> HealthScore:
    """Compute portfolio health from diversification, dividend quality and risk.

    Args express composition as fractions summing to ~1.0. Higher concentration
    (one asset/sector/country dominating) lowers the score and yields concrete,
    educational suggestions.
    """
    diversification = _diversification_score(weights_by_asset)
    sector = _diversification_score(weights_by_sector)
    country = _diversification_score(weights_by_country)
    cash = _cash_score(cash_weight)
    dividend = avg_dividend_safety if avg_dividend_safety is not None else Decimal(50)
    risk_component = max(Decimal(0), Decimal(100) - to_decimal(risk_score))

    components = {
        "diversification": diversification,
        "sector": sector,
        "country": country,
        "cash": cash,
        "dividend_quality": to_decimal(dividend),
        "risk": risk_component,
    }
    total = _clamp(sum(components.values(), Decimal(0)) / Decimal(len(components)))

    suggestions: list[str] = []
    top_asset = _max_weight(weights_by_asset)
    if top_asset and top_asset[1] > Decimal("0.20"):
        suggestions.append(
            f"Concentratie: {top_asset[0]} is {top_asset[1]:.0%} van de portefeuille — "
            "overweeg meer spreiding."
        )
    top_sector = _max_weight(weights_by_sector)
    if top_sector and top_sector[1] > Decimal("0.35"):
        suggestions.append(
            f"Sector {top_sector[0]} weegt {top_sector[1]:.0%} — sectorspreiding kan beter."
        )
    if to_decimal(cash_weight) > Decimal("0.20"):
        suggestions.append("Hoge cashpositie — geld staat mogelijk onbenut t.o.v. je doelen.")
    if to_decimal(cash_weight) < Decimal("0.02"):
        suggestions.append("Zeer lage cashbuffer — overweeg een reserve voor flexibiliteit.")

    return HealthScore(total=total, components=components, suggestions=suggestions)


def _diversification_score(weights: dict[str, Decimal]) -> Decimal:
    """Herfindahl-Hirschman-based diversification (higher = more diversified)."""
    if not weights:
        return Decimal(50)
    hhi = sum((to_decimal(w) ** 2 for w in weights.values()), Decimal(0))
    # HHI ranges (0, 1]; invert and scale to 0–100.
    return _clamp((Decimal(1) - hhi) * Decimal(100))


def _cash_score(cash_weight: Decimal) -> Decimal:
    c = to_decimal(cash_weight)
    if Decimal("0.02") <= c <= Decimal("0.10"):
        return Decimal(90)
    if c <= Decimal("0.20"):
        return Decimal(70)
    return Decimal(45)


def _max_weight(weights: dict[str, Decimal]) -> tuple[str, Decimal] | None:
    if not weights:
        return None
    key = max(weights, key=lambda k: to_decimal(weights[k]))
    return key, to_decimal(weights[key])
