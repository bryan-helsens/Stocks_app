"""Tests voor momentum_breakout_v3 — elke regel uit de docstring wordt bewezen."""

from __future__ import annotations

import pytest

from momentum_breakout_v3 import (
    BreakoutConfig, BreakoutGate, RiskModelV3, TrailManager,
)
from rsi_dip_buyer_v2 import Candle, ManageAction, MarketRegime


# --------------------------------------------------------------------------- #
# testdata: uptrend → consolidatie → (optioneel) breakout-bar
# --------------------------------------------------------------------------- #
def make_bar(ts: float, o: float, c: float, wick: float = 0.012,
             vol: float = 1000.0) -> Candle:
    hi = max(o, c) * (1 + wick)
    lo = min(o, c) * (1 - wick)
    return Candle(ts, o, hi, lo, c, vol)


def base_series(n: int = 260, drift: float = 0.0013,
                wick: float = 0.012) -> list[Candle]:
    """Gestage uptrend met brede ranges (ATR% ~2.4 → kosten-gate tevreden)."""
    p, out = 100.0, []
    for i in range(n):
        o = p
        c = p * (1 + drift)
        out.append(make_bar(float(i), o, c, wick))
        p = c
    return out


def with_consolidation(candles: list[Candle], bars: int = 30,
                       wick: float = 0.012) -> list[Candle]:
    """Vlakke periode ónder de laatste top, zodat er een niveau ontstaat."""
    out = list(candles)
    lvl = out[-1].close * 0.985
    for i in range(bars):
        ts = out[-1].ts + 1
        out.append(make_bar(ts, lvl, lvl, wick))
    return out


def with_breakout(candles: list[Candle], vol_mult: float = 2.0,
                  ext_atr: float = 0.5, wick: float = 0.012) -> list[Candle]:
    """Breakout-bar: close boven de hoogste high van de laatste 55 bars."""
    out = list(candles)
    cfg = BreakoutConfig()
    level = max(c.high for c in out[-cfg.breakout_lookback:])
    from rsi_dip_buyer_v2 import atr
    cur_atr = atr(out, cfg.atr_period)[-1]
    close = level + ext_atr * cur_atr
    out.append(make_bar(out[-1].ts + 1, out[-1].close, close, wick,
                        vol=1000.0 * vol_mult))
    return out


BREAKOUT = with_breakout(with_consolidation(base_series()))


# --------------------------------------------------------------------------- #
# entry-gate
# --------------------------------------------------------------------------- #
def test_gate_accepts_clean_breakout():
    dec = BreakoutGate(BreakoutConfig()).evaluate("BTC-EUR", BREAKOUT)
    assert dec.allowed, dec.reasons
    assert dec.score >= 65
    assert dec.stop_price is not None and dec.stop_price < BREAKOUT[-1].close
    assert dec.take_profit is not None and dec.take_profit > BREAKOUT[-1].close


def test_gate_refuses_without_breakout():
    candles = with_consolidation(base_series())      # consolidatie, geen uitbraak
    dec = BreakoutGate(BreakoutConfig()).evaluate("BTC-EUR", candles)
    assert not dec.allowed
    assert any("geen breakout" in r for r in dec.reasons)


def test_gate_refuses_downtrend():
    down = base_series(drift=-0.0013)
    # forceer een 'breakout'-achtige laatste bar omhoog — trend blijft down
    last = down[-1]
    down.append(make_bar(last.ts + 1, last.close, last.close * 1.05))
    dec = BreakoutGate(BreakoutConfig()).evaluate("BTC-EUR", down)
    assert not dec.allowed
    assert any("geen uptrend" in r for r in dec.reasons)


def test_gate_refuses_overextended_chase():
    candles = with_breakout(with_consolidation(base_series()), ext_atr=3.0)
    dec = BreakoutGate(BreakoutConfig()).evaluate("BTC-EUR", candles)
    assert not dec.allowed
    assert any("niet chasen" in r for r in dec.reasons)


def test_gate_refuses_bear_regime():
    dec = BreakoutGate(BreakoutConfig()).evaluate("BTC-EUR", BREAKOUT,
                                                  regime=MarketRegime.BEAR)
    assert not dec.allowed
    assert any("BEAR" in r for r in dec.reasons)


def test_gate_refuses_too_little_data():
    dec = BreakoutGate(BreakoutConfig()).evaluate("BTC-EUR", BREAKOUT[:100])
    assert not dec.allowed


def test_gate_respects_allow_and_denylist():
    cfg = BreakoutConfig(allowlist=("BTC", "ETH"))
    assert not BreakoutGate(cfg).evaluate("SOL-EUR", BREAKOUT).allowed
    cfg = BreakoutConfig(denylist=("BTC",))
    assert not BreakoutGate(cfg).evaluate("BTC-EUR", BREAKOUT).allowed


def test_cost_gate_refuses_tight_atr_setups():
    # wick 0.003 → ATR% ~0.76: binnen de ATR-band [0.5, 6.0], maar de stop
    # wordt 2.5×0.76 ≈ 1.9% en kosten 0.85% = 0.45R > 0.30R → cost-gate
    tight = with_breakout(
        with_consolidation(base_series(wick=0.003), wick=0.003), wick=0.003)
    dec = BreakoutGate(BreakoutConfig()).evaluate("BTC-EUR", tight)
    assert not dec.allowed
    assert any("te duur om te traden" in r for r in dec.reasons)


def test_cost_gate_math_matches_promise():
    cfg = BreakoutConfig()
    dec = BreakoutGate(cfg).evaluate("BTC-EUR", BREAKOUT)
    assert dec.allowed
    price = BREAKOUT[-1].close
    stop_pct = 100.0 * (price - dec.stop_price) / price
    cost_pct = cfg.fee_pct_round_trip + cfg.stop_slippage_pct
    assert cost_pct / stop_pct <= cfg.max_cost_per_risk + 1e-9


def test_volume_bonus_counts():
    hi = BreakoutGate(BreakoutConfig()).evaluate(
        "BTC-EUR", with_breakout(with_consolidation(base_series()), vol_mult=2.0))
    lo = BreakoutGate(BreakoutConfig()).evaluate(
        "BTC-EUR", with_breakout(with_consolidation(base_series()), vol_mult=1.0))
    assert hi.score == lo.score + 20.0


# --------------------------------------------------------------------------- #
# sizing
# --------------------------------------------------------------------------- #
def test_riskmodel_sizes_fixed_fraction_and_partial_only():
    cfg = BreakoutConfig()
    dec = BreakoutGate(cfg).evaluate("BTC-EUR", BREAKOUT)
    plan = RiskModelV3(cfg).plan("BTC-EUR", 1000.0, dec,
                                 price=BREAKOUT[-1].close)
    assert plan is not None
    assert plan.risk_amount == pytest.approx(7.5)          # 0.75% van 1000
    assert plan.quantity * (plan.entry - plan.stop) == pytest.approx(7.5)
    # één partial-level op +2R voor 50% — de rest heeft géén doel (trail)
    assert len(plan.tp_levels) == 1
    tp_price, frac = plan.tp_levels[0]
    assert frac == pytest.approx(0.5)
    assert tp_price == pytest.approx(
        plan.entry + 2.0 * (plan.entry - plan.stop))


def test_riskmodel_skips_below_min_notional():
    cfg = BreakoutConfig()
    dec = BreakoutGate(cfg).evaluate("BTC-EUR", BREAKOUT)
    assert RiskModelV3(cfg).plan("BTC-EUR", 5.0, dec,
                                 price=BREAKOUT[-1].close) is None


# --------------------------------------------------------------------------- #
# trade-management
# --------------------------------------------------------------------------- #
def rising_after_entry(entry: float, bars: int, step: float = 0.01,
                       wick: float = 0.012) -> list[Candle]:
    out = list(BREAKOUT)
    p = entry
    for i in range(bars):
        o = p
        p = p * (1 + step)
        out.append(make_bar(out[-1].ts + 1, o, p, wick))
    return out


def test_chandelier_raises_stop_and_never_lowers():
    cfg = BreakoutConfig()
    entry = BREAKOUT[-1].close
    stop0 = entry * 0.94
    mgr = TrailManager(cfg)
    candles = rising_after_entry(entry, 10)
    d1 = mgr.manage(entry_price=entry, stop_loss=stop0, break_even_armed=True,
                    bars_held=10, candles=candles)
    assert d1.action is ManageAction.RAISE_STOP and d1.new_stop > stop0
    # koers zakt daarna: trail mag NIET omlaag (nieuwe stop ≤ vorige → HOLD)
    fall = list(candles)
    p = fall[-1].close
    for _ in range(3):
        o = p
        p *= 0.985
        fall.append(make_bar(fall[-1].ts + 1, o, p, 0.003))
    d2 = mgr.manage(entry_price=entry, stop_loss=d1.new_stop,
                    break_even_armed=True, bars_held=13, candles=fall)
    assert d2.action is not ManageAction.RAISE_STOP or \
        d2.new_stop >= d1.new_stop


def test_breakeven_armed_at_1r():
    cfg = BreakoutConfig()
    entry = BREAKOUT[-1].close
    risk = entry * 0.06
    candles = rising_after_entry(entry, 7)           # ruim boven +1R
    d = TrailManager(cfg).manage(entry_price=entry, stop_loss=entry - risk,
                                 break_even_armed=False, bars_held=7,
                                 candles=candles)
    assert d.action is ManageAction.RAISE_STOP
    assert d.new_stop >= entry


def test_crash_bar_exits_immediately():
    cfg = BreakoutConfig()
    entry = BREAKOUT[-1].close
    candles = rising_after_entry(entry, 5)
    last = candles[-1]
    from rsi_dip_buyer_v2 import atr
    cur_atr = atr(candles, cfg.atr_period)[-1]
    crash_close = last.close - (cfg.crash_bar_drop_atr + 0.5) * cur_atr
    candles.append(Candle(last.ts + 1, last.close, last.close,
                          crash_close * 0.999, crash_close, 1000.0))
    d = TrailManager(cfg).manage(entry_price=entry,
                                 stop_loss=entry - 3 * cur_atr,
                                 break_even_armed=False, bars_held=6,
                                 candles=candles)
    assert d.action is ManageAction.EXIT_NOW
    assert "dump" in d.reason


def test_bear_regime_exits_immediately():
    entry = BREAKOUT[-1].close
    d = TrailManager(BreakoutConfig()).manage(
        entry_price=entry, stop_loss=entry * 0.94, break_even_armed=False,
        bars_held=3, candles=BREAKOUT, regime=MarketRegime.BEAR)
    assert d.action is ManageAction.EXIT_NOW
    assert "BEAR" in d.reason


def test_time_stop_kills_dead_breakout_but_not_winners():
    cfg = BreakoutConfig(time_stop_bars=10)
    entry = BREAKOUT[-1].close
    # dood: koers blijft exact op entry hangen (rustige bars)
    flat = list(BREAKOUT)
    for _ in range(12):
        flat.append(make_bar(flat[-1].ts + 1, entry, entry, 0.001))
    d = TrailManager(cfg).manage(entry_price=entry, stop_loss=entry * 0.94,
                                 break_even_armed=False, bars_held=12,
                                 candles=flat)
    assert d.action is ManageAction.EXIT_NOW and "time-stop" in d.reason
    # winnaar: ruim boven time_stop_min_r → geen time-stop
    up = rising_after_entry(entry, 12)
    d = TrailManager(cfg).manage(entry_price=entry, stop_loss=entry * 0.94,
                                 break_even_armed=True, bars_held=12,
                                 candles=up)
    assert d.action is not ManageAction.EXIT_NOW


# --------------------------------------------------------------------------- #
# integratie: backtest-engine draait v3 met begrensde verliezen
# --------------------------------------------------------------------------- #
def test_backtest_v3_smoke_losses_bounded():
    import backtest as bt
    markets = ["BTC-EUR", "ETH-EUR", "SOL-EUR"]
    series = {m: bt.synthetic(days=30, seed=21 + i, kind=k)
              for i, (m, k) in enumerate(zip(markets, ["up", "mixed", "down"]))}
    res = bt.run_v3(series, series["BTC-EUR"], BreakoutConfig())
    assert res.equity_curve[-1] > 0
    for t in res.trades:
        assert t.r_multiple > -2.0, f"verlies te groot: {t}"
