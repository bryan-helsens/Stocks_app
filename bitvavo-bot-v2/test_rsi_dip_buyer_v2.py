"""Tests voor rsi_dip_buyer_v2 — elke bewering uit de module wordt bewezen.

Draaien:  pytest test_rsi_dip_buyer_v2.py -v
"""

from __future__ import annotations

import math

import pytest

from rsi_dip_buyer_v2 import (
    Candle, CrashGuard, DailyCircuitBreaker, EntryGate, ManageAction,
    MarketRegime, PositionManager, RiskModel, StrategyConfig, atr, ema, rsi,
)

CFG = StrategyConfig()


# --------------------------------------------------------------------------- #
# helpers: synthetische candle-reeksen
# --------------------------------------------------------------------------- #
def flat_candles(n: int, price: float = 100.0, wiggle: float = 0.3) -> list[Candle]:
    """Zijwaartse markt met kleine, deterministische wiggle (geen randomness)."""
    out = []
    for i in range(n):
        d = wiggle * math.sin(i * 0.7)
        c = price + d
        out.append(Candle(i, c - 0.1, c + 0.2, c - 0.2, c))
    return out


def uptrend_with_dip(n: int = 260, start: float = 100.0,
                     wide_ranges: bool = True) -> list[Candle]:
    """Gestage uptrend, dip van ~10 rode bars, dan 2 groene draai-bars.

    ``wide_ranges=True`` geeft ±1.2% wieken -> ATR ~2.4% -> stop ~4.8% ->
    kosten (0.85%) ~ 0.18R: passeert de cost-gate. Met ``wide_ranges=False``
    is ATR ~0.3% en hoort de cost-gate juist te weigeren.
    """
    hw = 0.012 if wide_ranges else 0.0015      # wiek-breedte
    out, p = [], start
    for i in range(n - 12):
        p *= 1.003                      # +0.3%/bar uptrend
        out.append(Candle(i, p / 1.002, p * (1 + hw), p / (1 + hw + 0.002), p))
    for i in range(10):                 # dip: kleine rode bars
        prev = p
        p *= 0.994
        out.append(Candle(n - 12 + i, prev, prev * (1 + hw), p * (1 - hw), p))
    for i in range(2):                  # draai: groene bars
        prev = p
        p *= 1.004
        out.append(Candle(n - 2 + i, prev, p * (1 + hw), prev * (1 - hw), p))
    return out


def downtrend(n: int = 260, start: float = 100.0) -> list[Candle]:
    out, p = [], start
    for i in range(n):
        prev = p
        p *= 0.997
        out.append(Candle(i, prev, prev * 1.001, p * 0.999, p))
    return out


def with_dump(candles: list[Candle], bars: int = 3, drop_per_bar: float = 0.04) -> list[Candle]:
    """Plak een agressieve dump (−4%/bar) achter een reeks."""
    out = list(candles)
    p = out[-1].close
    for i in range(bars):
        prev = p
        p *= (1.0 - drop_per_bar)
        out.append(Candle(out[-1].ts + 1, prev, prev * 1.001, p * 0.998, p))
    return out


# --------------------------------------------------------------------------- #
# indicatoren
# --------------------------------------------------------------------------- #
def test_ema_converges_to_constant():
    vals = [50.0] * 300
    assert ema(vals, 200)[-1] == pytest.approx(50.0)


def test_rsi_100_when_only_gains_and_low_when_only_losses():
    up = [float(i) for i in range(1, 40)]
    down = [float(40 - i) for i in range(1, 40)]
    assert rsi(up, 14)[-1] == pytest.approx(100.0)
    assert rsi(down, 14)[-1] < 5.0


def test_rsi_midrange_on_alternating():
    seq = [100 + (1 if i % 2 else -1) for i in range(60)]
    v = rsi([float(x) for x in seq], 14)[-1]
    assert 35.0 < v < 65.0


def test_atr_matches_constant_range():
    # elke bar heeft high-low = 2.0 en geen gaps → ATR convergeert naar 2.0
    cs = [Candle(i, 100, 101, 99, 100) for i in range(100)]
    assert atr(cs, 14)[-1] == pytest.approx(2.0, rel=1e-6)


# --------------------------------------------------------------------------- #
# entry-gate: professioneel kopen / niet kopen
# --------------------------------------------------------------------------- #
def test_gate_buys_quality_dip_in_uptrend():
    d = EntryGate(CFG).evaluate("ETHEUR", uptrend_with_dip())
    assert d.allowed, d.reasons
    assert d.score >= CFG.min_quality_score
    assert d.stop_price is not None and d.take_profit is not None


def test_gate_refuses_downtrend():
    d = EntryGate(CFG).evaluate("ETHEUR", downtrend())
    assert not d.allowed
    assert any("uptrend" in r.lower() for r in d.reasons)


def test_gate_refuses_falling_knife():
    """RSI dipte maar draait nog niet omhoog → wachten."""
    cs = uptrend_with_dip()[:-2]        # knip de 2 groene draai-bars eraf
    # verleng de dip met nóg een rode bar zodat rsi[-1] < rsi[-2]
    p = cs[-1].close
    cs.append(Candle(cs[-1].ts + 1, p, p * 1.0005, p * 0.993, p * 0.994))
    d = EntryGate(CFG).evaluate("ETHEUR", cs)
    assert not d.allowed
    assert any("draai" in r or "valt nog" in r for r in d.reasons)


def test_gate_refuses_no_setup_in_flat_market():
    d = EntryGate(CFG).evaluate("BTCEUR", flat_candles(300))
    assert not d.allowed


def test_gate_refuses_wild_volatility():
    """ATR% boven de band (small-cap ruis zoals FET/NEAR) → skip."""
    cfg = StrategyConfig(max_atr_pct=0.10)      # zet band kunstmatig laag
    d = EntryGate(cfg).evaluate("FETEUR", uptrend_with_dip())
    assert not d.allowed
    assert any("ATR" in r and "band" in r for r in d.reasons)


def test_gate_respects_deny_and_allowlist():
    cfg_deny = StrategyConfig(denylist=("FET",))
    assert not EntryGate(cfg_deny).evaluate("FETEUR", uptrend_with_dip()).allowed
    cfg_allow = StrategyConfig(allowlist=("BTC", "ETH"))
    assert not EntryGate(cfg_allow).evaluate("SOLEUR", uptrend_with_dip()).allowed


def test_gate_blocks_all_entries_in_bear_regime():
    d = EntryGate(CFG).evaluate("ETHEUR", uptrend_with_dip(),
                                regime=MarketRegime.BEAR)
    assert not d.allowed
    assert any("BEAR" in r for r in d.reasons)


def test_gate_never_buys_into_active_dump():
    cs = with_dump(uptrend_with_dip(), bars=2, drop_per_bar=0.05)
    d = EntryGate(CFG).evaluate("ETHEUR", cs)
    assert not d.allowed


# --------------------------------------------------------------------------- #
# risicomodel: positieve R/R en correcte sizing
# --------------------------------------------------------------------------- #
def test_planned_trade_has_target_rr_and_correct_size():
    gate, rm = EntryGate(CFG), RiskModel(CFG)
    cs = uptrend_with_dip()
    d = gate.evaluate("ETHEUR", cs)
    assert d.allowed
    plan = rm.plan("ETHEUR", equity=100.0, decision=d, price=cs[-1].close)
    assert plan is not None
    assert plan.rr == pytest.approx(CFG.rr_target, rel=1e-6)
    # sizing: qty × (entry − stop) == risk_amount == 0.75% van 100
    assert plan.quantity * (plan.entry - plan.stop) == pytest.approx(0.75, rel=1e-9)


def test_break_even_winrate_below_v1_winrate():
    """Kern van de fix: benodigde winrate bij 1.6R < v1's werkelijke 40.5%."""
    needed = 1.0 / (1.0 + CFG.rr_target)
    assert needed < 0.405, f"benodigde winrate {needed:.1%} moet < 40.5% zijn"


def test_skip_below_min_notional():
    gate, rm = EntryGate(CFG), RiskModel(CFG)
    cs = uptrend_with_dip()
    d = gate.evaluate("ETHEUR", cs)
    plan = rm.plan("ETHEUR", equity=1.0, decision=d, price=cs[-1].close)  # mini-equity
    assert plan is None


# --------------------------------------------------------------------------- #
# crash-interceptor: verlies << volle stop
# --------------------------------------------------------------------------- #
def test_single_bar_shock_triggers_exit_now():
    cs = flat_candles(60)
    p = cs[-1].close
    cs.append(Candle(999, p, p, p * 0.94, p * 0.945))    # −5.5% in één bar
    cur_atr = atr(cs, 14)[-1]
    assert CrashGuard(CFG).bar_check(cs, cur_atr) is ManageAction.EXIT_NOW


def test_three_bar_velocity_triggers_exit_now():
    cs = with_dump(flat_candles(60), bars=3, drop_per_bar=0.025)  # 3× −2.5%
    cur_atr = atr(cs[:-3], 14)[-1]       # ATR van vóór de dump (zoals live)
    assert CrashGuard(CFG).bar_check(cs, cur_atr) is ManageAction.EXIT_NOW


def test_accelerating_red_bars_tighten_stop():
    cs = flat_candles(60)
    p = cs[-1].close
    cur_atr = atr(cs, 14)[-1]
    # bar 1: rood met body ~0.8×ATR ; bar 2: rood met body ~1.9× bar 1
    b1 = 0.8 * cur_atr
    cs.append(Candle(998, p, p * 1.0001, p - b1 * 1.1, p - b1))
    p2 = cs[-1].close
    b2 = 1.9 * b1
    cs.append(Candle(999, p2, p2 * 1.0001, p2 - b2 * 1.05, p2 - b2))
    assert CrashGuard(CFG).bar_check(cs, cur_atr) is ManageAction.RAISE_STOP


def test_quiet_market_holds():
    cs = flat_candles(60)
    cur_atr = atr(cs, 14)[-1]
    assert CrashGuard(CFG).bar_check(cs, cur_atr) is ManageAction.HOLD


def test_btc_dump_flips_market_regime_to_bear():
    btc = with_dump(flat_candles(60), bars=4, drop_per_bar=0.01)   # −4% totaal
    assert CrashGuard(CFG).market_regime(btc) is MarketRegime.BEAR
    assert CrashGuard(CFG).market_regime(flat_candles(60)) is not MarketRegime.BEAR


def test_interceptor_loss_smaller_than_full_stop():
    """Bewijs van de belofte: exit via interceptor < verlies bij volle stop.

    De shock-drempel (1.8×ATR) ligt bewust ONDER de stop-afstand (2×ATR):
    een dump-bar die de drempel raakt maar de stop nog niet, wordt direct
    verkocht → gerealiseerd verlies ≈ 0.9R i.p.v. 1R (+ gap/slippage).
    """
    cs = flat_candles(200)
    entry = cs[-1].close
    cur_atr = atr(cs, 14)[-1]
    stop = entry - CFG.stop_atr_mult * cur_atr          # klassieke 2×ATR-stop
    # dump-bar: body −1.9×ATR — boven de drempel, maar stop (−2×ATR) nog intact
    shock_close = entry - 1.9 * cur_atr
    assert shock_close > stop                           # stop is écht nog niet geraakt
    dump_bar = Candle(999, entry, entry, shock_close * 0.999, shock_close)
    cs2 = cs + [dump_bar]
    act = CrashGuard(CFG).bar_check(cs2, cur_atr)
    assert act is ManageAction.EXIT_NOW
    loss_interceptor = entry - shock_close
    loss_full_stop = entry - stop
    assert loss_interceptor < loss_full_stop            # kleiner verlies, QED


# --------------------------------------------------------------------------- #
# trade-management
# --------------------------------------------------------------------------- #
def _pos_candles_at_r(entry: float, stop: float, r: float, n: int = 60) -> list[Candle]:
    """Reeks die eindigt op prijs = entry + r×risk, rustig verloop."""
    target = entry + r * (entry - stop)
    cs = flat_candles(n, price=entry, wiggle=0.05)
    cs.append(Candle(n, target, target * 1.001, target * 0.999, target))
    return cs


def test_breakeven_move_at_1r():
    entry, stop = 100.0, 96.0
    cs = _pos_candles_at_r(entry, stop, r=1.05)
    d = PositionManager(CFG).manage(entry_price=entry, stop_loss=stop,
                                    break_even_armed=False, bars_held=10, candles=cs)
    assert d.action is ManageAction.RAISE_STOP
    assert d.new_stop is not None and d.new_stop >= entry   # ≥ entry (incl. fees)


def test_trailing_after_1_2r():
    entry, stop = 100.0, 96.0
    cs = _pos_candles_at_r(entry, stop, r=2.0)
    d = PositionManager(CFG).manage(entry_price=entry, stop_loss=entry,  # al BE
                                    break_even_armed=True, bars_held=20, candles=cs)
    assert d.action is ManageAction.RAISE_STOP
    assert d.new_stop is not None and d.new_stop > entry


def test_time_stop_kills_dead_capital():
    entry, stop = 100.0, 96.0
    cs = _pos_candles_at_r(entry, stop, r=0.05)             # gaat nergens heen
    d = PositionManager(CFG).manage(entry_price=entry, stop_loss=stop,
                                    break_even_armed=False,
                                    bars_held=CFG.time_stop_bars, candles=cs)
    assert d.action is ManageAction.EXIT_NOW
    assert "time-stop" in d.reason


def test_bear_regime_exits_position():
    entry, stop = 100.0, 96.0
    cs = _pos_candles_at_r(entry, stop, r=0.4)
    d = PositionManager(CFG).manage(entry_price=entry, stop_loss=stop,
                                    break_even_armed=False, bars_held=5,
                                    candles=cs, regime=MarketRegime.BEAR)
    assert d.action is ManageAction.EXIT_NOW


def test_healthy_position_is_held():
    entry, stop = 100.0, 96.0
    cs = _pos_candles_at_r(entry, stop, r=0.5)
    d = PositionManager(CFG).manage(entry_price=entry, stop_loss=stop,
                                    break_even_armed=False, bars_held=5, candles=cs)
    assert d.action is ManageAction.HOLD


# --------------------------------------------------------------------------- #
# circuit-breaker
# --------------------------------------------------------------------------- #
def test_circuit_breaker_trips_and_resets():
    cb = DailyCircuitBreaker(CFG)
    cb.new_day(100.0)
    assert cb.allow_trading(99.5)                # −0.5%: ok
    assert not cb.allow_trading(97.9)            # −2.1%: trip
    assert not cb.allow_trading(99.9)            # blijft dicht dezelfde dag
    cb.new_day(97.9)
    assert cb.allow_trading(97.9)                # nieuwe dag: weer open


# --------------------------------------------------------------------------- #
# nieuwe features: partial TP + cooldown
# --------------------------------------------------------------------------- #
def test_partial_tp_levels_average_equals_rr_target():
    """Gewogen gemiddelde van de TP-levels moet exact rr_target zijn."""
    from rsi_dip_buyer_v2 import EntryGate, RiskModel
    gate, rm = EntryGate(CFG), RiskModel(CFG)
    cs = uptrend_with_dip()
    d = gate.evaluate("ETHEUR", cs)
    plan = rm.plan("ETHEUR", equity=100.0, decision=d, price=cs[-1].close)
    assert plan is not None and len(plan.tp_levels) == 2
    fracs = [f for _, f in plan.tp_levels]
    assert sum(fracs) == pytest.approx(1.0)
    risk = plan.entry - plan.stop
    weighted_r = sum((p - plan.entry) / risk * f for p, f in plan.tp_levels)
    assert weighted_r == pytest.approx(CFG.rr_target, rel=1e-9)
    # TP1 ligt op partial_tp_at_r
    r1 = (plan.tp_levels[0][0] - plan.entry) / risk
    assert r1 == pytest.approx(CFG.partial_tp_at_r, rel=1e-9)


def test_single_tp_when_partial_disabled():
    from rsi_dip_buyer_v2 import EntryGate, RiskModel, StrategyConfig
    cfg = StrategyConfig(partial_tp_enabled=False)
    gate, rm = EntryGate(cfg), RiskModel(cfg)
    cs = uptrend_with_dip()
    d = gate.evaluate("ETHEUR", cs)
    plan = rm.plan("ETHEUR", equity=100.0, decision=d, price=cs[-1].close)
    assert plan is not None and len(plan.tp_levels) == 1
    assert plan.rr == pytest.approx(cfg.rr_target, rel=1e-9)


def test_cooldown_blocks_reentry_then_expires():
    from rsi_dip_buyer_v2 import CooldownTracker
    cd = CooldownTracker(CFG)
    assert not cd.blocked("FETEUR", 100)
    cd.record_loss_exit("FETEUR", 100)
    assert cd.blocked("FETEUR", 100 + CFG.cooldown_bars_after_stop - 1)
    assert not cd.blocked("FETEUR", 100 + CFG.cooldown_bars_after_stop)
    assert not cd.blocked("ETHEUR", 101)     # ander symbool niet geblokkeerd


# --------------------------------------------------------------------------- #
# cost-gate: de fix uit de echte 60d-backtest (PF 0.21, worst -3.25R op 15m)
# --------------------------------------------------------------------------- #
def test_cost_gate_refuses_tight_atr_setups():
    """Krappe ATR (15m-achtig) -> kosten domineren R -> gate weigert."""
    cs = uptrend_with_dip(wide_ranges=False)       # ATR% ~0.3 -> stop ~0.6%
    d = EntryGate(CFG).evaluate("BTCEUR", cs)
    assert not d.allowed
    assert any("kosten" in r for r in d.reasons), d.reasons


def test_cost_gate_math_matches_promise():
    """Als de gate WEL toestaat, zijn kosten <= max_cost_per_risk van 1R."""
    cs = uptrend_with_dip(wide_ranges=True)
    d = EntryGate(CFG).evaluate("BTCEUR", cs)
    assert d.allowed, d.reasons
    price = cs[-1].close
    stop_pct = 100.0 * (price - d.stop_price) / price
    cost_pct = CFG.fee_pct_round_trip + CFG.stop_slippage_pct
    assert cost_pct / stop_pct <= CFG.max_cost_per_risk
