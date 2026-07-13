"""rsi_dip_buyer_v2 — professionele herbouw van de RSI-dip strategie.

Waarom v1 verloor (gemeten op 43 gesloten trades uit state.json):
    winrate 40.5% · gem. TP +2.06% · gem. SL −3.40% · payoff 0.56
    → benodigde winrate voor break-even: 64%  → structureel negatieve edge.
    Bovendien: fees = 43% van het totale verlies, en alle winst kwam uit
    majors (ETH/ARB/BTC) terwijl volatiele alts (FET/SOL/NEAR/XLM/INJ)
    vrijwel het hele verlies droegen.

Wat v2 anders doet:
  1. ENTRY-GATE  — koopt alléén als de setup een kwaliteitsscore >= drempel
     haalt: uptrend (EMA-stack), RSI-dip die al DRAAIT (geen vallend mes),
     volatiliteit binnen een band (sluit wilde small-caps automatisch uit),
     geen actieve crash, geen te grote afstand tot de trend.
  2. POSITIEVE R/R — stop = k×ATR (volatiliteitsproportioneel i.p.v. vast %),
     take-profit = rr_target × risico. Default 1.6R:
         break-even winrate = 1 / (1 + 1.6) = 38.5%  (v1 had 40.5% winrate!)
     → zelfs bij ongewijzigde winrate flipt de expectancy positief; de
     entry-gate moet de winrate daarbovenop verhogen.
  3. CRASH-INTERCEPTOR — detecteert een beginnende dump (bar-velocity,
     versnelling, marktregime via BTC) en verlaat de positie DIRECT tegen
     markt, ruim vóór de volle stop-loss wordt geraakt → verlies << 1R.
  4. TRADE-MANAGEMENT — break-even na +1R, ATR-trailing na +1.2R,
     time-stop (dood kapitaal eruit), dagelijkse circuit-breaker.

⚠️  Educatief. Eerst paper-traden. Geen enkele filter maakt verlies
    onmogelijk; het doel is de verdeling kantelen (kleine verliezen,
    grotere winsten, minder slechte entries).

Integratie: zie README_INTEGRATIE.md. De module is dependency-vrij
(pure Python + dataclasses) en heeft geen kennis van Bitvavo zelf —
je voedt hem candles en hij geeft beslissingen terug.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

__all__ = [
    "Candle", "StrategyConfig", "EntryDecision", "ManageAction", "ManageDecision",
    "PlannedTrade", "MarketRegime", "ema", "rsi", "atr",
    "EntryGate", "RiskModel", "CrashGuard", "PositionManager", "DailyCircuitBreaker",
    "CooldownTracker",
]


# --------------------------------------------------------------------------- #
# Data & config
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Candle:
    """OHLCV-bar. `ts` is een epoch-seconde of oplopende index."""
    ts: float
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(slots=True)
class StrategyConfig:
    # ---- indicators ----
    rsi_period: int = 14
    atr_period: int = 14
    ema_fast: int = 50
    ema_slow: int = 200

    # ---- entry-gate ----
    rsi_dip_level: float = 32.0        # RSI moet hieronder zijn geweest...
    rsi_turn_confirm: bool = True      # ...en alweer omhoog draaien (geen vallend mes)
    require_uptrend: bool = True       # close > EMA_slow én EMA_fast > EMA_slow
    max_dist_below_fast_atr: float = 3.0   # dip niet dieper dan k×ATR onder EMA_fast
    min_atr_pct: float = 0.15          # ATR% band: te stil = geen beweging,
    max_atr_pct: float = 4.0           # te wild = small-cap ruis (sluit FET-types uit)
    min_quality_score: float = 65.0    # gate-drempel (0–100)
    allowlist: tuple[str, ...] = ()    # optioneel: alleen deze symbolen (leeg = alle)
    denylist: tuple[str, ...] = ()     # optioneel: nooit deze symbolen

    # ---- risico & targets ----
    stop_atr_mult: float = 2.0         # stop = entry − 2×ATR
    rr_target: float = 1.6             # gemiddelde TP = entry + 1.6 × risico
    risk_per_trade_pct: float = 0.75   # % van equity dat één trade mag riskeren
    min_notional: float = 5.0          # exchange-minimum
    fee_pct_round_trip: float = 0.30   # meegenomen in edge-check

    # ---- partial take-profit (sluit aan op take_profit_levels/size_fraction) --
    # 50% eraf bij +1R (stop gaat dan naar break-even), rest naar een verder
    # doel zodat het GEWOGEN gemiddelde exact rr_target blijft:
    #     tp2_r = (rr_target − f×tp1_r) / (1−f)  → default (1.6−0.5)/0.5 = 2.2R
    partial_tp_enabled: bool = True
    partial_tp_at_r: float = 1.0
    partial_tp_fraction: float = 0.5

    # ---- cooldown na stop-loss (v1 kocht FET 6×, INJ 5×, SOL 4× opnieuw
    #      terwijl de coin bleef vallen — dit blokkeert dat gedrag) ----
    cooldown_bars_after_stop: int = 48   # bv. 48×15m = 12u niet opnieuw instappen

    # ---- crash-interceptor ----
    # BELANGRIJK: beide drempels liggen ONDER stop_atr_mult (2.0), zodat de
    # interceptor vuurt vóórdat de volle stop geraakt wordt → verlies < 1R.
    crash_bar_drop_atr: float = 1.8    # één bar-body valt > 1.8×ATR → EXIT_NOW (~0.9R)
    crash_velocity_atr: float = 2.5    # som van laatste 3 bars < −2.5×ATR → EXIT_NOW
    crash_accel_ratio: float = 1.8     # laatste bar > 1.8× de vorige bar (versnellend) én beide rood → TIGHTEN
    market_crash_pct: float = 2.5      # BTC −2.5% binnen het venster → regime BEAR: exit alts, geen nieuwe entries
    market_window_bars: int = 12

    # ---- trade-management ----
    breakeven_at_r: float = 1.0        # stop naar entry (+ fees) na +1R
    trail_start_r: float = 1.2         # daarna ATR-trailing
    trail_atr_mult: float = 1.5
    time_stop_bars: int = 96           # (bv. 96×15m = 24u) niets bereikt → eruit
    time_stop_min_r: float = 0.3       # alleen time-stop als trade < +0.3R staat

    # ---- portefeuille ----
    max_open_positions: int = 4
    max_daily_loss_pct: float = 2.0    # circuit-breaker: dag −2% → stop met traden


class MarketRegime(str, Enum):
    RISK_ON = "RISK_ON"
    NEUTRAL = "NEUTRAL"
    BEAR = "BEAR"          # marktbrede dump gedetecteerd (BTC-proxy)


class ManageAction(str, Enum):
    HOLD = "HOLD"
    RAISE_STOP = "RAISE_STOP"          # nieuwe (hogere) stop plaatsen
    EXIT_NOW = "EXIT_NOW"              # direct market-sell (crash / regime / time-stop)


# --------------------------------------------------------------------------- #
# Indicatoren (Wilder-smoothing, dependency-vrij)
# --------------------------------------------------------------------------- #
def ema(values: Sequence[float], period: int) -> list[float]:
    """Exponentieel voortschrijdend gemiddelde; eerste `period` waarden = SMA-seed."""
    if len(values) < period:
        return []
    k = 2.0 / (period + 1.0)
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1.0 - k))
    return out


def rsi(closes: Sequence[float], period: int = 14) -> list[float]:
    """Wilder RSI. Retourneert één waarde per bar vanaf bar `period`."""
    if len(closes) <= period:
        return []
    gains, losses = [], []
    for prev, cur in zip(closes, closes[1:]):
        d = cur - prev
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    out = []
    for g, l in zip(gains[period:], losses[period:]):
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
        out.append(100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l))
    # seed-waarde vooraan zodat lengte = len(closes) - period
    first = 100.0 if sum(losses[:period]) == 0 else \
        100.0 - 100.0 / (1.0 + (sum(gains[:period]) / max(sum(losses[:period]), 1e-12)))
    return [first] + out


def atr(candles: Sequence[Candle], period: int = 14) -> list[float]:
    """Wilder ATR; retourneert één waarde per bar vanaf bar `period`."""
    if len(candles) <= period:
        return []
    trs = []
    for prev, cur in zip(candles, candles[1:]):
        trs.append(max(cur.high - cur.low,
                       abs(cur.high - prev.close),
                       abs(cur.low - prev.close)))
    out = [sum(trs[:period]) / period]
    for tr in trs[period:]:
        out.append((out[-1] * (period - 1) + tr) / period)
    return out


# --------------------------------------------------------------------------- #
# 1) Entry-gate: professioneel kopen (of níet kopen)
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class EntryDecision:
    allowed: bool
    score: float                       # 0–100
    reasons: list[str] = field(default_factory=list)   # waarom wel/niet
    stop_price: float | None = None
    take_profit: float | None = None
    atr_value: float | None = None


class EntryGate:
    """Beoordeelt of een RSI-dip een KOOP waard is. Default: nee, tenzij."""

    def __init__(self, cfg: StrategyConfig) -> None:
        self.cfg = cfg

    def evaluate(self, symbol: str, candles: Sequence[Candle],
                 regime: MarketRegime = MarketRegime.NEUTRAL) -> EntryDecision:
        cfg = self.cfg
        need = max(cfg.ema_slow, cfg.rsi_period, cfg.atr_period) + 3
        if len(candles) < need:
            return EntryDecision(False, 0.0, [f"te weinig data (<{need} bars)"])

        base = symbol.replace("EUR", "").replace("-", "")
        if cfg.allowlist and base not in cfg.allowlist:
            return EntryDecision(False, 0.0, [f"{base} niet in allowlist"])
        if base in cfg.denylist:
            return EntryDecision(False, 0.0, [f"{base} in denylist"])
        if regime is MarketRegime.BEAR:
            return EntryDecision(False, 0.0, ["marktregime BEAR: geen nieuwe entries"])

        closes = [c.close for c in candles]
        price = closes[-1]
        ema_fast = ema(closes, cfg.ema_fast)[-1]
        ema_slow = ema(closes, cfg.ema_slow)[-1]
        rsis = rsi(closes, cfg.rsi_period)
        atrs = atr(candles, cfg.atr_period)
        cur_atr = atrs[-1]
        atr_pct = 100.0 * cur_atr / price

        score = 0.0
        reasons: list[str] = []

        # -- 1. Trendfilter (40 pt): dips kopen kan, maar alleen in een uptrend.
        uptrend = price > ema_slow and ema_fast > ema_slow
        if uptrend:
            score += 40.0
            reasons.append("uptrend OK (close>EMA200, EMA50>EMA200)")
        else:
            reasons.append("GEEN uptrend — dit was v1's grootste lek")
            if cfg.require_uptrend:
                return EntryDecision(False, score, reasons)

        # -- 2. RSI-dip die al draait (25 pt): geen vallend mes vangen.
        dipped = min(rsis[-3:]) < cfg.rsi_dip_level
        turning = rsis[-1] > rsis[-2]
        if dipped and (turning or not cfg.rsi_turn_confirm):
            score += 25.0
            reasons.append(f"RSI-dip ({min(rsis[-3:]):.1f}) draait omhoog")
        elif dipped:
            reasons.append("RSI dipte maar valt nog — wachten op draai")
            return EntryDecision(False, score, reasons)
        else:
            reasons.append("geen RSI-dip — geen setup")
            return EntryDecision(False, score, reasons)

        # -- 3. Volatiliteitsband (20 pt): sluit de FET/NEAR-klasse ruis uit.
        if cfg.min_atr_pct <= atr_pct <= cfg.max_atr_pct:
            score += 20.0
            reasons.append(f"volatiliteit OK (ATR {atr_pct:.2f}%)")
        else:
            reasons.append(f"ATR {atr_pct:.2f}% buiten band "
                           f"[{cfg.min_atr_pct}–{cfg.max_atr_pct}] — sla over")
            return EntryDecision(False, score, reasons)

        # -- 4. Dip-diepte begrensd (15 pt): te ver onder EMA_fast = kapotte markt.
        dist_atr = (ema_fast - price) / cur_atr if cur_atr > 0 else 99.0
        if dist_atr <= cfg.max_dist_below_fast_atr:
            score += 15.0
            reasons.append(f"dip-diepte OK ({dist_atr:.1f}×ATR onder EMA{cfg.ema_fast})")
        else:
            reasons.append(f"dip te diep ({dist_atr:.1f}×ATR) — structuur kapot")
            return EntryDecision(False, score, reasons)

        # -- 5. Crash-check op de instap zelf.
        guard = CrashGuard(cfg)
        if guard.bar_check(candles, cur_atr) is ManageAction.EXIT_NOW:
            reasons.append("actieve dump gedetecteerd — nooit in een crash kopen")
            return EntryDecision(False, score, reasons)

        if score < cfg.min_quality_score:
            reasons.append(f"score {score:.0f} < drempel {cfg.min_quality_score:.0f}")
            return EntryDecision(False, score, reasons)

        # -- Stop/TP volgens RiskModel; edge-check inclusief fees.
        stop = price - cfg.stop_atr_mult * cur_atr
        risk = price - stop
        tp = price + cfg.rr_target * risk
        tp_pct = 100.0 * (tp - price) / price
        if tp_pct <= cfg.fee_pct_round_trip * 2.0:
            reasons.append("TP te klein t.o.v. fees — trade heeft geen nut")
            return EntryDecision(False, score, reasons)

        reasons.append(f"KOOP: score {score:.0f}, stop {stop:.6g} (2×ATR), "
                       f"TP {tp:.6g} ({cfg.rr_target}R)")
        return EntryDecision(True, score, reasons, stop_price=stop,
                             take_profit=tp, atr_value=cur_atr)


# --------------------------------------------------------------------------- #
# 2) Risico & sizing
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class PlannedTrade:
    symbol: str
    entry: float
    stop: float
    take_profit: float                 # gewogen gemiddelde doel (= rr_target)
    quantity: float
    risk_amount: float                 # € dat op het spel staat (excl. fees)
    rr: float
    #: [(prijs, size_fraction), ...] — mapt 1-op-1 op jouw take_profit_levels.
    tp_levels: list[tuple[float, float]] = field(default_factory=list)


class RiskModel:
    """Fixed-fractional sizing: elke trade riskeert hetzelfde % van equity."""

    def __init__(self, cfg: StrategyConfig) -> None:
        self.cfg = cfg

    def plan(self, symbol: str, equity: float, decision: EntryDecision,
             price: float) -> PlannedTrade | None:
        cfg = self.cfg
        if not decision.allowed or decision.stop_price is None:
            return None
        risk_per_unit = price - decision.stop_price
        if risk_per_unit <= 0:
            return None
        risk_amount = equity * cfg.risk_per_trade_pct / 100.0
        qty = risk_amount / risk_per_unit
        if qty * price < cfg.min_notional:
            return None                # te klein voor de exchange → skip

        # TP-levels: één level op rr_target, of gesplitst (partial) zó dat het
        # gewogen gemiddelde exact rr_target blijft.
        if cfg.partial_tp_enabled and 0.0 < cfg.partial_tp_fraction < 1.0:
            f, tp1_r = cfg.partial_tp_fraction, cfg.partial_tp_at_r
            tp2_r = (cfg.rr_target - f * tp1_r) / (1.0 - f)
            if tp2_r <= tp1_r:          # onzinnige config → val terug op één level
                levels = [(price + cfg.rr_target * risk_per_unit, 1.0)]
            else:
                levels = [(price + tp1_r * risk_per_unit, f),
                          (price + tp2_r * risk_per_unit, 1.0 - f)]
        else:
            levels = [(price + cfg.rr_target * risk_per_unit, 1.0)]

        avg_tp = sum(p * fr for p, fr in levels)
        rr = (avg_tp - price) / risk_per_unit
        return PlannedTrade(symbol=symbol, entry=price, stop=decision.stop_price,
                            take_profit=avg_tp, quantity=qty,
                            risk_amount=risk_amount, rr=rr, tp_levels=levels)


class CooldownTracker:
    """Blokkeert her-instap in een symbool vlak na een stop-loss/crash-exit.

    Gemeten v1-gedrag: dezelfde vallende coin werd keer op keer opnieuw
    gekocht (FET 6×, INJ 5×, SOL 4× in één week). Roep `record_loss_exit`
    aan bij elke SL/EXIT_NOW en check `blocked` vóór de EntryGate.
    Tijd is in *bars* (geef een bar-index of epoch/interval door).
    """

    def __init__(self, cfg: StrategyConfig) -> None:
        self.cfg = cfg
        self._last_loss_bar: dict[str, int] = {}

    def record_loss_exit(self, symbol: str, bar_index: int) -> None:
        self._last_loss_bar[symbol] = bar_index

    def blocked(self, symbol: str, bar_index: int) -> bool:
        last = self._last_loss_bar.get(symbol)
        if last is None:
            return False
        return (bar_index - last) < self.cfg.cooldown_bars_after_stop


# --------------------------------------------------------------------------- #
# 3) Crash-interceptor: verliezen klein houden vóór de stop geraakt wordt
# --------------------------------------------------------------------------- #
class CrashGuard:
    """Detecteert een beginnende dump en grijpt in.

    Drie triggers op het symbool zelf, plus een marktbrede (BTC-proxy):
      a) single-bar shock : één bar daalt > crash_bar_drop_atr × ATR
      b) velocity         : som van de laatste 3 bars < −crash_velocity_atr × ATR
      c) acceleratie      : twee rode bars waarvan de laatste ≥ ratio× de vorige
                            → TIGHTEN (stop direct onder de laatste low)
      d) marktregime      : BTC valt > market_crash_pct% binnen het venster
                            → regime BEAR: alle alt-longs EXIT_NOW, geen entries
    a en b zijn EXIT_NOW: beter −0.8R nu dan −1R+slippage straks.
    """

    def __init__(self, cfg: StrategyConfig) -> None:
        self.cfg = cfg

    # ---- symbool-checks ----
    def bar_check(self, candles: Sequence[Candle], cur_atr: float) -> ManageAction:
        cfg = self.cfg
        if len(candles) < 4 or cur_atr <= 0:
            return ManageAction.HOLD
        c1, c2, c3 = candles[-3], candles[-2], candles[-1]

        # a) single-bar shock
        if (c3.open - c3.close) > cfg.crash_bar_drop_atr * cur_atr:
            return ManageAction.EXIT_NOW
        # b) 3-bar velocity
        drop3 = (c1.open - c3.close)
        if drop3 > cfg.crash_velocity_atr * cur_atr:
            return ManageAction.EXIT_NOW
        # c) versnellende rode bars → stop aantrekken
        red2 = c2.close < c2.open
        red3 = c3.close < c3.open
        if red2 and red3:
            body2 = c2.open - c2.close
            body3 = c3.open - c3.close
            if body2 > 0 and body3 >= cfg.crash_accel_ratio * body2 \
               and body3 > 0.75 * cur_atr:
                return ManageAction.RAISE_STOP
        return ManageAction.HOLD

    # ---- marktbrede check (voer BTC-candles hetzelfde timeframe) ----
    def market_regime(self, btc_candles: Sequence[Candle]) -> MarketRegime:
        cfg = self.cfg
        w = cfg.market_window_bars
        if len(btc_candles) < w + 1:
            return MarketRegime.NEUTRAL
        start = btc_candles[-w - 1].close
        now = btc_candles[-1].close
        ret_pct = 100.0 * (now - start) / start
        if ret_pct <= -cfg.market_crash_pct:
            return MarketRegime.BEAR
        if ret_pct >= 0:
            return MarketRegime.RISK_ON
        return MarketRegime.NEUTRAL


# --------------------------------------------------------------------------- #
# 4) Trade-management: break-even, trailing, time-stop, crash-overrides
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class ManageDecision:
    action: ManageAction
    new_stop: float | None = None
    reason: str = ""


class PositionManager:
    """Beheert een open long. Aanroepen op elke afgesloten bar.

    Sluit aan op jouw state-model: `entry_price`, `stop_loss`,
    `break_even_armed`, `bars_held` — geef die velden door en verwerk het
    resultaat terug in de positie + (paper-)orders.
    """

    def __init__(self, cfg: StrategyConfig) -> None:
        self.cfg = cfg
        self.guard = CrashGuard(cfg)

    def manage(self, *, entry_price: float, stop_loss: float,
               break_even_armed: bool, bars_held: int,
               candles: Sequence[Candle],
               regime: MarketRegime = MarketRegime.NEUTRAL) -> ManageDecision:
        cfg = self.cfg
        price = candles[-1].close
        atrs = atr(candles, cfg.atr_period)
        cur_atr = atrs[-1] if atrs else 0.0
        risk = max(entry_price - stop_loss, 1e-12)
        r_now = (price - entry_price) / risk

        # -- 0. marktbrede crash: alt-longs direct sluiten.
        if regime is MarketRegime.BEAR:
            return ManageDecision(ManageAction.EXIT_NOW,
                                  reason="marktregime BEAR (BTC-dump): exit alle longs")

        # -- 1. crash-interceptor op het symbool zelf.
        crash = self.guard.bar_check(candles, cur_atr)
        if crash is ManageAction.EXIT_NOW:
            return ManageDecision(ManageAction.EXIT_NOW,
                                  reason="dump gedetecteerd: direct eruit (verlies < volle stop)")
        if crash is ManageAction.RAISE_STOP:
            tight = candles[-1].low - 0.25 * cur_atr
            if tight > stop_loss:
                return ManageDecision(ManageAction.RAISE_STOP, new_stop=tight,
                                      reason="versnellende daling: stop onder laatste low")

        # -- 2. break-even zodra +1R bereikt is.
        if not break_even_armed and r_now >= cfg.breakeven_at_r:
            be = entry_price * (1.0 + cfg.fee_pct_round_trip / 100.0)
            if be > stop_loss:
                return ManageDecision(ManageAction.RAISE_STOP, new_stop=be,
                                      reason=f"+{cfg.breakeven_at_r}R bereikt: stop naar break-even")

        # -- 3. ATR-trailing vanaf trail_start_r.
        if r_now >= cfg.trail_start_r and cur_atr > 0:
            trail = price - cfg.trail_atr_mult * cur_atr
            if trail > stop_loss:
                return ManageDecision(ManageAction.RAISE_STOP, new_stop=trail,
                                      reason=f"trailing {cfg.trail_atr_mult}×ATR")

        # -- 4. time-stop: dood kapitaal opruimen.
        if bars_held >= cfg.time_stop_bars and r_now < cfg.time_stop_min_r:
            return ManageDecision(ManageAction.EXIT_NOW,
                                  reason=f"time-stop: {bars_held} bars zonder progressie")

        return ManageDecision(ManageAction.HOLD, reason=f"houden ({r_now:+.2f}R)")


# --------------------------------------------------------------------------- #
# 5) Dagelijkse circuit-breaker
# --------------------------------------------------------------------------- #
class DailyCircuitBreaker:
    """Stop met traden zodra het dagverlies de limiet raakt."""

    def __init__(self, cfg: StrategyConfig) -> None:
        self.cfg = cfg
        self._day_start_equity: float | None = None
        self._tripped = False

    def new_day(self, equity: float) -> None:
        self._day_start_equity = equity
        self._tripped = False

    def allow_trading(self, equity: float) -> bool:
        if self._day_start_equity is None:
            self._day_start_equity = equity
        if self._tripped:
            return False
        dd_pct = 100.0 * (self._day_start_equity - equity) / self._day_start_equity
        if dd_pct >= self.cfg.max_daily_loss_pct:
            self._tripped = True
            return False
        return True
