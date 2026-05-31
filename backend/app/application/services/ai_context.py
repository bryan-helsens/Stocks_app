"""Deterministic AI context builders.

Turn portfolio/position data into a compact, fully pre-computed context bundle
for the LLM. ALL numbers here come from the domain services — the LLM receives
facts and only interprets them (no numeric hallucination). Educational only.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.application.services.portfolio import PortfolioSummary
from app.domain.entities import Fundamentals
from app.domain.services import risk
from app.domain.services.scoring import score_asset


def _pct(part: Decimal, whole: Decimal) -> float:
    if whole <= 0:
        return 0.0
    return float(round(part / whole, 4))


def build_portfolio_context(summary: PortfolioSummary) -> dict:
    """Build a whole-portfolio context bundle with allocations and risk."""
    total = summary.total_value if summary.total_value > 0 else summary.total_invested

    by_asset: dict[str, Decimal] = {}
    by_sector: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    by_country: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    by_class: dict[str, Decimal] = defaultdict(lambda: Decimal(0))

    for h in summary.holdings:
        value = h.market_value if h.market_value is not None else h.position.total_invested
        by_asset[h.asset.ticker] = value
        by_sector[h.asset.sector or "Unknown"] += value
        by_country[h.asset.country or "Unknown"] += value
        by_class[h.asset.asset_class.value] += value

    asset_weights = {k: _pct(v, total) for k, v in by_asset.items()}
    sector_weights = {k: _pct(v, total) for k, v in by_sector.items()}
    country_weights = {k: _pct(v, total) for k, v in by_country.items()}
    class_weights = {k: _pct(v, total) for k, v in by_class.items()}

    weight_decimals = [Decimal(str(w)) for w in asset_weights.values()]
    concentration = risk.concentration_hhi(weight_decimals)

    top_holdings = sorted(asset_weights.items(), key=lambda kv: kv[1], reverse=True)[:5]

    return {
        "totals": {
            "total_value": str(summary.total_value),
            "total_invested": str(summary.total_invested),
            "unrealized_pnl": str(summary.total_unrealized),
            "realized_pnl": str(summary.realized_pnl),
            "currency": summary.base_currency,
            "num_holdings": len(summary.holdings),
        },
        "allocation": {
            "by_asset_class": class_weights,
            "by_sector": sector_weights,
            "by_country": country_weights,
        },
        "top_holdings": [{"ticker": t, "weight": w} for t, w in top_holdings],
        "concentration_hhi": float(round(concentration, 4)),
        "note": "Alle gewichten en cijfers zijn deterministisch vooraf berekend.",
    }


def build_position_context(
    ticker: str,
    name: str,
    quantity: Decimal,
    avg_cost: Decimal,
    price: Decimal | None,
    fundamentals: Fundamentals | None,
    portfolio_weight: float,
) -> dict:
    """Build a single-position context bundle including the quality score."""
    market_value = (quantity * price) if price is not None else None
    unrealized = (market_value - quantity * avg_cost) if market_value is not None else None

    score = None
    ratios: dict = {}
    if fundamentals is not None:
        s = score_asset(fundamentals)
        score = {
            "total": str(s.total),
            "valuation": str(s.valuation),
            "growth": str(s.growth),
            "health": str(s.health),
            "dividend": str(s.dividend),
            "breakdown": s.breakdown,
        }
        ratios = {
            "pe": _s(fundamentals.pe),
            "forward_pe": _s(fundamentals.forward_pe),
            "peg": _s(fundamentals.peg),
            "roe": _s(fundamentals.roe),
            "roic": _s(fundamentals.roic),
            "debt_equity": _s(fundamentals.debt_equity),
            "payout_ratio": _s(fundamentals.payout_ratio),
            "revenue_growth": _s(fundamentals.revenue_growth),
            "earnings_growth": _s(fundamentals.earnings_growth),
            "dividend_growth": _s(fundamentals.dividend_growth),
        }

    return {
        "asset": {"ticker": ticker, "name": name},
        "position": {
            "quantity": str(quantity),
            "avg_cost": str(avg_cost),
            "price": _s(price),
            "market_value": _s(market_value),
            "unrealized_pnl": _s(unrealized),
            "portfolio_weight": portfolio_weight,
        },
        "quality_score": score,
        "ratios": ratios,
        "note": "Alle ratio's en scores zijn deterministisch vooraf berekend.",
    }


def _s(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
