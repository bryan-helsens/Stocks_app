"""Valuation models: DCF, Dividend Discount Model, multiples and a blend.

All models are transparent and assumption-driven. Outputs are
**informational/educational** (M9) — small changes in assumptions move fair
value materially, which the UI surfaces via "show assumptions".
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.entities import Valuation
from app.domain.value_objects.enums import ValuationMethod, ValuationVerdict
from app.domain.value_objects.money import to_decimal

# Margin-of-safety band that counts as "fairly valued".
_FAIR_BAND = Decimal("0.10")  # within ±10% of fair value


def _verdict(margin_of_safety: Decimal | None) -> ValuationVerdict:
    """Map margin of safety to a verdict.

    margin_of_safety = (fair_value - price) / fair_value.
    Positive ⇒ price below fair value ⇒ undervalued.
    """
    if margin_of_safety is None:
        return ValuationVerdict.FAIR
    if margin_of_safety > _FAIR_BAND:
        return ValuationVerdict.UNDERVALUED
    if margin_of_safety < -_FAIR_BAND:
        return ValuationVerdict.OVERVALUED
    return ValuationVerdict.FAIR


def margin_of_safety(fair_value: Decimal | None, price: Decimal) -> Decimal | None:
    """Return (fair_value - price) / fair_value, or None if not computable."""
    if fair_value is None:
        return None
    fv = to_decimal(fair_value)
    if fv <= 0:
        return None
    return (fv - to_decimal(price)) / fv


def dcf_fair_value(
    free_cash_flow: Decimal,
    shares_outstanding: Decimal,
    growth_rate: Decimal,
    discount_rate: Decimal,
    terminal_growth: Decimal,
    years: int,
    current_price: Decimal,
) -> Valuation:
    """Two-stage discounted cash flow per share.

    Stage 1 grows FCF at *growth_rate* for *years*, discounting each year at
    *discount_rate*. A Gordon terminal value uses *terminal_growth*. The
    enterprise value is divided by *shares_outstanding* for per-share fair value.

    Returns a ``FAIR`` verdict with ``fair_value=None`` when inputs are
    degenerate (non-positive shares, discount <= terminal growth, FCF <= 0).
    """
    fcf = to_decimal(free_cash_flow)
    shares = to_decimal(shares_outstanding)
    g = to_decimal(growth_rate)
    r = to_decimal(discount_rate)
    tg = to_decimal(terminal_growth)

    if shares <= 0 or fcf <= 0 or r <= tg:
        return Valuation(
            method=ValuationMethod.DCF,
            fair_value=None,
            current_price=to_decimal(current_price),
            margin_of_safety=None,
            verdict=ValuationVerdict.FAIR,
            assumptions={"note": "DCF not reliable for these inputs"},
        )

    pv_sum = Decimal(0)
    cash = fcf
    one = Decimal(1)
    for year in range(1, max(1, years) + 1):
        cash = cash * (one + g)
        pv_sum += cash / ((one + r) ** year)

    terminal_value = (cash * (one + tg)) / (r - tg)
    pv_terminal = terminal_value / ((one + r) ** years)
    enterprise_value = pv_sum + pv_terminal
    fair_per_share = enterprise_value / shares

    mos = margin_of_safety(fair_per_share, current_price)
    return Valuation(
        method=ValuationMethod.DCF,
        fair_value=fair_per_share,
        current_price=to_decimal(current_price),
        margin_of_safety=mos,
        verdict=_verdict(mos),
        assumptions={
            "growth_rate": str(g),
            "discount_rate": str(r),
            "terminal_growth": str(tg),
            "years": years,
        },
    )


def ddm_fair_value(
    dividend_per_share: Decimal,
    growth_rate: Decimal,
    required_return: Decimal,
    current_price: Decimal,
) -> Valuation:
    """Gordon Growth Dividend Discount Model: FV = D1 / (r - g).

    D1 is next year's dividend (current DPS grown by *growth_rate*). Requires
    ``required_return > growth_rate`` and a positive dividend, otherwise returns
    an unreliable ``FAIR`` result.
    """
    d0 = to_decimal(dividend_per_share)
    g = to_decimal(growth_rate)
    r = to_decimal(required_return)

    if d0 <= 0 or r <= g:
        return Valuation(
            method=ValuationMethod.DDM,
            fair_value=None,
            current_price=to_decimal(current_price),
            margin_of_safety=None,
            verdict=ValuationVerdict.FAIR,
            assumptions={"note": "DDM requires positive dividend and r > g"},
        )

    d1 = d0 * (Decimal(1) + g)
    fair = d1 / (r - g)
    mos = margin_of_safety(fair, current_price)
    return Valuation(
        method=ValuationMethod.DDM,
        fair_value=fair,
        current_price=to_decimal(current_price),
        margin_of_safety=mos,
        verdict=_verdict(mos),
        assumptions={"growth_rate": str(g), "required_return": str(r)},
    )


def multiples_fair_value(
    eps: Decimal,
    peer_pe: Decimal,
    current_price: Decimal,
) -> Valuation:
    """Relative valuation: fair value = EPS × peer P/E."""
    eps_d = to_decimal(eps)
    pe = to_decimal(peer_pe)
    if eps_d <= 0 or pe <= 0:
        return Valuation(
            method=ValuationMethod.MULTIPLES,
            fair_value=None,
            current_price=to_decimal(current_price),
            margin_of_safety=None,
            verdict=ValuationVerdict.FAIR,
            assumptions={"note": "multiples need positive EPS and peer P/E"},
        )
    fair = eps_d * pe
    mos = margin_of_safety(fair, current_price)
    return Valuation(
        method=ValuationMethod.MULTIPLES,
        fair_value=fair,
        current_price=to_decimal(current_price),
        margin_of_safety=mos,
        verdict=_verdict(mos),
        assumptions={"eps": str(eps_d), "peer_pe": str(pe)},
    )


def blended_valuation(
    valuations: list[Valuation],
    weights: dict[ValuationMethod, Decimal] | None = None,
) -> Valuation:
    """Combine multiple model outputs into a weighted blended fair value.

    Models that produced no fair value are skipped. When *weights* is omitted
    each contributing model is weighted equally.
    """
    contributing = [v for v in valuations if v.fair_value is not None]
    if not contributing:
        price = valuations[0].current_price if valuations else None
        return Valuation(
            method=ValuationMethod.BLENDED,
            fair_value=None,
            current_price=price,
            margin_of_safety=None,
            verdict=ValuationVerdict.FAIR,
            assumptions={"note": "no model produced a fair value"},
        )

    weights = weights or {}
    weighted_sum = Decimal(0)
    weight_total = Decimal(0)
    used: dict[str, str] = {}
    for v in contributing:
        w = weights.get(v.method, Decimal(1))
        weighted_sum += (v.fair_value or Decimal(0)) * w
        weight_total += w
        used[v.method.value] = str(v.fair_value)

    fair = weighted_sum / weight_total if weight_total > 0 else None
    price = contributing[0].current_price or Decimal(0)
    mos = margin_of_safety(fair, price)
    return Valuation(
        method=ValuationMethod.BLENDED,
        fair_value=fair,
        current_price=price,
        margin_of_safety=mos,
        verdict=_verdict(mos),
        assumptions={"components": used},
    )
