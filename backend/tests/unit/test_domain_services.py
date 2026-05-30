"""Unit tests for the pure domain services.

These exercise the financial core (FIFO P/L, dividends, valuation, FIRE,
scenarios, scoring, risk, Belgian tax) without any I/O. They are the regression
safety-net for the most correctness-sensitive code in the system.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.entities import Fundamentals, Transaction
from app.domain.services import dividends, fire, pnl, risk, scenarios, scoring, tax_be, valuation
from app.domain.services.pnl import InsufficientSharesError
from app.domain.value_objects.enums import AssetClass, TransactionType, ValuationVerdict
from app.domain.value_objects.money import CurrencyMismatchError, Money

PID = uuid4()
AID = uuid4()
UID = uuid4()


def _tx(type_, **kw) -> Transaction:
    return Transaction(
        id=uuid4(), user_id=UID, portfolio_id=PID, asset_id=AID,
        type=type_, trade_date=kw.pop("dt", datetime(2025, 1, 1)),
        currency=kw.pop("currency", "EUR"), **kw,
    )


# --------------------------------------------------------------------------- #
# Money
# --------------------------------------------------------------------------- #
def test_money_addition_same_currency():
    assert (Money("10.50", "EUR") + Money("0.25", "EUR")).amount == Decimal("10.75000000")


def test_money_rejects_cross_currency():
    with pytest.raises(CurrencyMismatchError):
        _ = Money(1, "EUR") + Money(1, "USD")


def test_money_no_float_artefacts():
    # 0.1 + 0.2 must equal exactly 0.3
    assert (Money(0.1, "EUR") + Money(0.2, "EUR")).rounded(2) == Decimal("0.30")


def test_money_convert():
    assert Money(100, "USD").convert("EUR", "0.9").amount == Decimal("90.00000000")


# --------------------------------------------------------------------------- #
# FIFO P/L
# --------------------------------------------------------------------------- #
def test_fifo_realized_pnl():
    txs = [
        _tx(TransactionType.BUY, quantity=Decimal(10), price=Decimal(100),
            dt=datetime(2025, 1, 1)),
        _tx(TransactionType.BUY, quantity=Decimal(10), price=Decimal(120),
            dt=datetime(2025, 2, 1)),
        _tx(TransactionType.SELL, quantity=Decimal(15), price=Decimal(150),
            dt=datetime(2025, 3, 1)),
    ]
    result = pnl.build_position(PID, AID, txs)
    # FIFO: sell 15 @150 = 2250 proceeds.
    # cost removed = 10@100 + 5@120 = 1000 + 600 = 1600 -> realized 650.
    assert result.realized_pnl == Decimal("650.00000000")
    # remaining 5 shares from the 120 lot.
    assert result.position.quantity == Decimal("5.00000000")
    assert result.position.avg_cost == Decimal("120.00000000")


def test_buy_fees_increase_cost_basis():
    txs = [_tx(TransactionType.BUY, quantity=Decimal(10), price=Decimal(100),
               fee=Decimal(10))]
    result = pnl.build_position(PID, AID, txs)
    assert result.position.avg_cost == Decimal("101.00000000")  # (1000+10)/10


def test_sell_more_than_held_raises():
    txs = [
        _tx(TransactionType.BUY, quantity=Decimal(5), price=Decimal(100)),
        _tx(TransactionType.SELL, quantity=Decimal(10), price=Decimal(110),
            dt=datetime(2025, 2, 1)),
    ]
    with pytest.raises(InsufficientSharesError):
        pnl.build_position(PID, AID, txs)


def test_stock_split_preserves_cost_basis():
    txs = [
        _tx(TransactionType.BUY, quantity=Decimal(10), price=Decimal(100),
            dt=datetime(2025, 1, 1)),
        _tx(TransactionType.STOCK_SPLIT, split_ratio=Decimal(2),
            dt=datetime(2025, 2, 1)),
    ]
    result = pnl.build_position(PID, AID, txs)
    assert result.position.quantity == Decimal("20.00000000")
    assert result.position.avg_cost == Decimal("50.00000000")
    assert result.position.total_invested == Decimal("1000.00000000")


def test_dividends_accumulate_net_of_tax():
    txs = [
        _tx(TransactionType.BUY, quantity=Decimal(10), price=Decimal(100)),
        _tx(TransactionType.DIVIDEND, gross_amount=Decimal(50), tax=Decimal(15),
            dt=datetime(2025, 2, 1)),
    ]
    result = pnl.build_position(PID, AID, txs)
    assert result.total_dividends == Decimal("35.00000000")


# --------------------------------------------------------------------------- #
# Dividends
# --------------------------------------------------------------------------- #
def test_yield_on_cost():
    assert dividends.yield_on_cost(Decimal(4), Decimal(80)) == Decimal("0.05000000")


def test_current_yield_undefined_for_zero_price():
    assert dividends.current_yield(Decimal(4), Decimal(0)) is None


def test_dividend_cagr():
    cagr = dividends.dividend_cagr([(2020, Decimal(100)), (2025, Decimal(161))])
    # (161/100)^(1/5)-1 ~= 0.10
    assert cagr is not None
    assert Decimal("0.09") < cagr < Decimal("0.11")


def test_project_future_dividends():
    proj = dividends.project_future_dividends(Decimal(100), Decimal(2), Decimal("0.10"), years=2)
    assert proj[0] == Decimal("220.00000000")  # 100 * (2*1.1)
    assert proj[1] == Decimal("242.00000000")  # 100 * (2*1.1*1.1)


def test_dividend_safety_penalises_cut():
    safe = dividends.dividend_safety(Decimal("0.4"), Decimal("0.5"), Decimal("0.5"), 12, False)
    risky = dividends.dividend_safety(Decimal("1.2"), Decimal("1.3"), Decimal(3), 0, True)
    assert safe.score > risky.score
    assert safe.label == "Safe"
    assert risky.label == "At risk"


# --------------------------------------------------------------------------- #
# Valuation
# --------------------------------------------------------------------------- #
def test_ddm_fair_value():
    v = valuation.ddm_fair_value(Decimal(2), Decimal("0.05"), Decimal("0.09"), Decimal(60))
    # D1 = 2.1, FV = 2.1 / 0.04 = 52.5 -> price 60 -> overvalued
    assert v.fair_value == Decimal("52.50000000")
    assert v.verdict == ValuationVerdict.OVERVALUED


def test_ddm_requires_r_gt_g():
    v = valuation.ddm_fair_value(Decimal(2), Decimal("0.10"), Decimal("0.08"), Decimal(60))
    assert v.fair_value is None


def test_margin_of_safety_sign():
    # fair 100, price 80 -> +20% margin (undervalued)
    assert valuation.margin_of_safety(Decimal(100), Decimal(80)) == Decimal("0.20000000")


def test_multiples_and_blend():
    m = valuation.multiples_fair_value(Decimal(5), Decimal(15), Decimal(60))
    assert m.fair_value == Decimal("75.00000000")
    blended = valuation.blended_valuation([m])
    assert blended.fair_value == Decimal("75.00000000")


# --------------------------------------------------------------------------- #
# FIRE
# --------------------------------------------------------------------------- #
def test_fire_targets():
    t = fire.fire_targets(Decimal(30000), Decimal("0.04"), Decimal(100000),
                          Decimal("0.07"), years_to_traditional_retirement=0)
    assert t.full_number == Decimal("750000.00000000")  # 30000 / 0.04
    assert t.coast == t.full_number  # horizon 0 -> no discount


def test_project_to_fi_reaches_target():
    proj = fire.project_to_fi(
        current_value=Decimal(100000),
        monthly_contribution=Decimal(1000),
        expected_return=Decimal("0.07"),
        target_value=Decimal(200000),
        today=date(2025, 1, 1),
    )
    assert proj.fi_date is not None
    assert proj.years_to_fi is not None and proj.years_to_fi > 0


def test_project_to_fi_already_met():
    proj = fire.project_to_fi(Decimal(300000), Decimal(0), Decimal("0.05"),
                              Decimal(200000), date(2025, 1, 1))
    assert proj.years_to_fi == Decimal(0)


# --------------------------------------------------------------------------- #
# Scenarios
# --------------------------------------------------------------------------- #
def test_scenario_crash_reduces_value():
    base = scenarios.simulate(Decimal(100000), Decimal(500), Decimal("0.07"), 10, name="base")
    crash = scenarios.simulate(Decimal(100000), Decimal(500), Decimal("0.07"), 10,
                               name="crash", one_off_crash_pct=Decimal("0.30"), crash_year=5)
    assert crash.final_value < base.final_value


def test_monte_carlo_band_ordering():
    band = scenarios.monte_carlo(Decimal(100000), Decimal(500), Decimal("0.07"),
                                 Decimal("0.15"), 10, runs=200)
    assert band.p10 <= band.p50 <= band.p90


# --------------------------------------------------------------------------- #
# Scoring & risk
# --------------------------------------------------------------------------- #
def test_score_asset_handles_missing_data():
    f = Fundamentals(asset_id=AID, as_of=date(2025, 1, 1), pe=Decimal(15), peg=Decimal("1.2"))
    s = scoring.score_asset(f)
    assert Decimal(0) <= s.total <= Decimal(100)
    # Growth/health/dividend unknown -> marked n/a
    assert s.breakdown["growth"] == "n/a"


def test_portfolio_health_flags_concentration():
    h = scoring.portfolio_health(
        weights_by_asset={"AAPL": Decimal("0.5"), "MSFT": Decimal("0.5")},
        weights_by_sector={"Tech": Decimal("1.0")},
        weights_by_country={"US": Decimal("1.0")},
        cash_weight=Decimal("0.05"),
        avg_dividend_safety=Decimal(70),
        risk_score=Decimal(60),
    )
    assert any("Concentratie" in s for s in h.suggestions)


def test_risk_score_monotonic_in_volatility():
    low = risk.risk_score(Decimal("0.10"), Decimal("0.2"), Decimal("0.1"))
    high = risk.risk_score(Decimal("0.35"), Decimal("0.2"), Decimal("0.1"))
    assert high > low


# --------------------------------------------------------------------------- #
# Belgian tax (informational)
# --------------------------------------------------------------------------- #
def test_tob_stock_rate_and_cap():
    r = tax_be.compute_tob(Decimal(10000), AssetClass.STOCK)
    assert r.raw_tax == Decimal("35.00000000")  # 0.35%
    big = tax_be.compute_tob(Decimal(10_000_000), AssetClass.STOCK)
    assert big.capped_tax == Decimal("1600")  # cap applies


def test_foreign_dividend_double_taxation():
    line = tax_be.compute_dividend_tax(
        gross=Decimal(100), source_country="US", foreign_withholding_rate=Decimal("0.15"),
    )
    # 100 - 15 foreign = 85; RV 30% of 85 = 25.5; net = 59.5
    assert line.foreign_withholding == Decimal("15.00000000")
    assert line.belgian_rv == Decimal("25.50000000")
    assert line.net == Decimal("59.50000000")
    assert line.is_foreign is True


def test_belgian_dividend_no_foreign_wht():
    line = tax_be.compute_dividend_tax(Decimal(100), "BE", Decimal("0.15"))
    assert line.foreign_withholding == Decimal(0)
    assert line.belgian_rv == Decimal("30.00000000")


def test_build_tax_summary_aggregates():
    lines = [
        tax_be.compute_dividend_tax(Decimal(100), "US", Decimal("0.15"), asset_label="O"),
        tax_be.compute_dividend_tax(Decimal(50), "BE", Decimal(0), asset_label="KBC"),
    ]
    summary = tax_be.build_tax_summary(2025, lines, tob_total=Decimal(20), fees_total=Decimal(10))
    assert summary.foreign_dividends_gross == Decimal("100.00000000")
    assert summary.belgian_dividends_gross == Decimal("50.00000000")
    assert summary.tob_total == Decimal("20.00000000")
    assert "informatief" in summary.disclaimer.lower()
