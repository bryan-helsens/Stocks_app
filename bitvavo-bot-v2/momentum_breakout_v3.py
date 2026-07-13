"""Bitvavo bot v3 — momentum/breakout: koop STERKTE, rijd de trend, trail de stop.

Waarom deze richting (na de v1/v2-data):
  • v1 (dips kopen, 15m) verloor in élke configuratie: PF 0.46–0.65.
  • v2 (dips kopen met kwaliteits- en kostenfilters) beschermt kapitaal
    perfect, maar vindt bijna geen betaalbare setups: dips in een uptrend
    zijn zeldzaam én krap (kleine ATR → kosten-gate weigert terecht).
  • Crypto trendt hard. Een breakout-systeem koopt juist als de markt
    beweegt — dan is de ATR vanzelf groot, dus de stop breed, dus de vaste
    kosten klein in R-termen. Het vecht mét de kostenstructuur mee in
    plaats van ertegen.

De regels (alles configureerbaar via BreakoutConfig):
  ENTRY — alléén als alles klopt:
    1. uptrend: close > EMA200 én EMA50 > EMA200
    2. breakout: close boven de hoogste HIGH van de laatste N bars
       (close-bevestiging — geen intrabar-fakeouts)
    3. niet te ver: close max `max_extension_atr`×ATR boven het
       breakout-niveau (geen pump chasen)
    4. ATR-band + KOSTEN-GATE: fees+slippage ≤ `max_cost_per_risk`
       van het risico (dé les uit de echte v2-backtest)
    5. BTC-regime niet BEAR
  EXIT — verliezen klein, winnaars laten lopen:
    • initiële stop: `stop_atr_mult`×ATR onder entry
    • partial: 50% eraf op +2R, stop naar break-even
    • rest: chandelier-trail (hoogste close sinds entry − `trail_atr_mult`×ATR)
    • crash-interceptor + BEAR-exit (hergebruikt uit v2)
    • time-stop: dode breakout na `time_stop_bars` zonder progressie

⚠️  Educatief. Geen financieel advies. Eerst falsifiëren met backtest.py,
    daarna pas (paper) draaien.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from rsi_dip_buyer_v2 import (
    Candle, CrashGuard, EntryDecision, ManageAction, ManageDecision,
    MarketRegime, PlannedTrade, atr, ema,
)

__all__ = ["BreakoutConfig", "BreakoutGate", "RiskModelV3", "TrailManager"]


# --------------------------------------------------------------------------- #
# configuratie
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class BreakoutConfig:
    # ---- indicators ----
    atr_period: int = 14
    ema_fast: int = 50
    ema_slow: int = 200
    ema_momentum: int = 20             # korte EMA als momentum-bevestiging

    # ---- entry ----
    breakout_lookback: int = 55        # close > hoogste high van N vorige bars
    require_uptrend: bool = True
    max_extension_atr: float = 1.5     # close max k×ATR boven het breakout-niveau
    volume_confirm: float = 1.3        # barvolume ≥ k× gemiddelde(20); 0 = uit
    min_atr_pct: float = 0.5           # te stil = geen trend om te rijden
    max_atr_pct: float = 6.0           # te wild = small-cap ruis
    min_quality_score: float = 65.0
    allowlist: tuple[str, ...] = ()
    denylist: tuple[str, ...] = ()

    # ---- kostenmodel (identiek aan v2 — dezelfde les) ----
    fee_pct_round_trip: float = 0.50   # 0.25% taker/zijde; 0.30 bij limit orders
    stop_slippage_pct: float = 0.35
    max_cost_per_risk: float = 0.30    # (fees+slip)/stop% ≤ 0.30, anders skip

    # ---- risico & sizing ----
    stop_atr_mult: float = 2.5         # breed: breakouts hebben ademruimte nodig
    risk_per_trade_pct: float = 0.75
    min_notional: float = 5.0

    # ---- exits ----
    partial_tp_enabled: bool = True
    partial_tp_at_r: float = 2.0       # 50% winst pakken op +2R
    partial_tp_fraction: float = 0.5
    trail_atr_mult: float = 3.0        # chandelier: hoogste close − 3×ATR
    breakeven_at_r: float = 1.0
    time_stop_bars: int = 48           # dode breakout na 48 bars (2 dagen op 1h)
    time_stop_min_r: float = 0.5

    # ---- crash-interceptor & marktregime (hergebruikt CrashGuard) ----
    crash_bar_drop_atr: float = 2.0
    crash_velocity_atr: float = 2.8
    crash_accel_ratio: float = 1.8
    market_crash_pct: float = 2.5
    market_window_bars: int = 12

    # ---- portefeuille ----
    cooldown_bars_after_stop: int = 24
    max_open_positions: int = 4
    max_daily_loss_pct: float = 2.0


# --------------------------------------------------------------------------- #
# 1) Entry-gate: koop alléén een bevestigde, betaalbare breakout
# --------------------------------------------------------------------------- #
class BreakoutGate:
    """Beoordeelt of een breakout een KOOP waard is. Default: nee, tenzij."""

    def __init__(self, cfg: BreakoutConfig) -> None:
        self.cfg = cfg

    def evaluate(self, symbol: str, candles: Sequence[Candle],
                 regime: MarketRegime = MarketRegime.NEUTRAL) -> EntryDecision:
        cfg = self.cfg
        need = max(cfg.ema_slow, cfg.breakout_lookback) + 3
        if len(candles) < need:
            return EntryDecision(False, 0.0, [f"te weinig data (<{need} bars)"])

        base = symbol.replace("EUR", "").replace("-", "")
        if cfg.allowlist and base not in cfg.allowlist:
            return EntryDecision(False, 0.0, [f"{base} niet in allowlist"])
        if base in cfg.denylist:
            return EntryDecision(False, 0.0, [f"{base} in denylist"])
        if regime is MarketRegime.BEAR:
            return EntryDecision(False, 0.0,
                                 ["marktregime BEAR: geen nieuwe entries"])

        closes = [c.close for c in candles]
        price = closes[-1]
        score, reasons = 0.0, []

        # 1. trendfilter
        e_fast = ema(closes, cfg.ema_fast)
        e_slow = ema(closes, cfg.ema_slow)
        uptrend = price > e_slow[-1] and e_fast[-1] > e_slow[-1]
        if uptrend:
            score += 40.0
            reasons.append("uptrend OK (close>EMA200, EMA50>EMA200)")
        elif cfg.require_uptrend:
            reasons.append("geen uptrend — breakout zonder trend is een gok")
            return EntryDecision(False, score, reasons)

        # 2. breakout: close boven de hoogste HIGH van de vorige N bars
        window = candles[-cfg.breakout_lookback - 1:-1]
        level = max(c.high for c in window)
        if price <= level:
            reasons.append(f"geen breakout: close {price:.6g} ≤ "
                           f"{cfg.breakout_lookback}-bar high {level:.6g}")
            return EntryDecision(False, score, reasons)
        score += 25.0
        reasons.append(f"breakout boven {cfg.breakout_lookback}-bar high "
                       f"{level:.6g}")

        # 3. volatiliteit + niet chasen
        atrs = atr(candles, cfg.atr_period)
        cur_atr = atrs[-1] if atrs else 0.0
        atr_pct = 100.0 * cur_atr / price if price > 0 else 0.0
        if not (cfg.min_atr_pct <= atr_pct <= cfg.max_atr_pct):
            reasons.append(f"ATR {atr_pct:.2f}% buiten band "
                           f"[{cfg.min_atr_pct}, {cfg.max_atr_pct}]")
            return EntryDecision(False, score, reasons)
        if cur_atr > 0 and (price - level) > cfg.max_extension_atr * cur_atr:
            reasons.append(f"te ver boven breakout-niveau "
                           f"(+{(price - level) / cur_atr:.1f}×ATR) — niet chasen")
            return EntryDecision(False, score, reasons)

        # 4. momentum-bevestiging (bonus)
        e_mom = ema(closes, cfg.ema_momentum)
        if len(e_mom) >= 2 and price > e_mom[-1] and e_mom[-1] > e_mom[-2]:
            score += 15.0
            reasons.append("momentum OK (close>EMA20 en EMA20 stijgt)")

        # 5. volume-bevestiging (bonus)
        vols = [c.volume for c in candles[-21:-1]]
        avg_vol = sum(vols) / len(vols) if vols else 0.0
        if cfg.volume_confirm <= 0:
            score += 20.0                      # check uitgezet → geen straf
        elif avg_vol > 0 and candles[-1].volume >= cfg.volume_confirm * avg_vol:
            score += 20.0
            reasons.append(f"volume {candles[-1].volume / avg_vol:.1f}× gemiddeld")

        if score < cfg.min_quality_score:
            reasons.append(f"score {score:.0f} < drempel "
                           f"{cfg.min_quality_score:.0f}")
            return EntryDecision(False, score, reasons)

        # 6. KOSTEN-GATE — identiek aan v2, dé les uit de echte backtest
        stop = price - cfg.stop_atr_mult * cur_atr
        risk = price - stop
        stop_pct = 100.0 * risk / price if price > 0 else 0.0
        cost_pct = cfg.fee_pct_round_trip + cfg.stop_slippage_pct
        cost_per_risk = cost_pct / stop_pct if stop_pct > 0 else 99.0
        if cost_per_risk > cfg.max_cost_per_risk:
            reasons.append(f"kosten {cost_pct:.2f}% = {cost_per_risk:.2f}R van "
                           f"het risico (stop {stop_pct:.2f}%) > max "
                           f"{cfg.max_cost_per_risk:.2f}R — te duur om te traden")
            return EntryDecision(False, score, reasons)

        tp_info = price + cfg.partial_tp_at_r * risk
        reasons.append(f"KOOP: score {score:.0f}, stop {stop:.6g} "
                       f"({stop_pct:.2f}%), partial-TP {tp_info:.6g} (+"
                       f"{cfg.partial_tp_at_r:.0f}R), rest trailt")
        return EntryDecision(True, score, reasons, stop_price=stop,
                             take_profit=tp_info, atr_value=cur_atr)


# --------------------------------------------------------------------------- #
# 2) Sizing: fixed-fractional, partial-TP-level; de rest heeft GEEN doel
# --------------------------------------------------------------------------- #
class RiskModelV3:
    """Zoals v2's RiskModel, maar trend-following: alleen een partial-TP-level;
    de rest van de positie loopt op de trailing stop (geen winstplafond)."""

    def __init__(self, cfg: BreakoutConfig) -> None:
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
            return None

        levels: list[tuple[float, float]] = []
        if cfg.partial_tp_enabled and 0.0 < cfg.partial_tp_fraction < 1.0:
            levels = [(price + cfg.partial_tp_at_r * risk_per_unit,
                       cfg.partial_tp_fraction)]
        tp_info = price + cfg.partial_tp_at_r * risk_per_unit
        return PlannedTrade(symbol=symbol, entry=price,
                            stop=decision.stop_price, take_profit=tp_info,
                            quantity=qty, risk_amount=risk_amount,
                            rr=cfg.partial_tp_at_r, tp_levels=levels)


# --------------------------------------------------------------------------- #
# 3) Trade-management: chandelier-trail + break-even + crash + time-stop
# --------------------------------------------------------------------------- #
class TrailManager:
    """Zelfde interface als v2's PositionManager (drop-in verwisselbaar).

    De chandelier-trail gebruikt de hoogste close sinds entry, afgeleid uit
    `bars_held` en het candle-venster — er hoeft dus geen extra state door
    de aanroeper bijgehouden te worden.
    """

    def __init__(self, cfg: BreakoutConfig) -> None:
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

        # -- 0. marktbrede crash: longs direct sluiten.
        if regime is MarketRegime.BEAR:
            return ManageDecision(ManageAction.EXIT_NOW,
                                  reason="marktregime BEAR (BTC-dump): exit alle longs")

        # -- 1. crash-interceptor op het symbool zelf.
        crash = self.guard.bar_check(candles, cur_atr)
        if crash is ManageAction.EXIT_NOW:
            return ManageDecision(ManageAction.EXIT_NOW,
                                  reason="dump gedetecteerd: direct eruit")
        if crash is ManageAction.RAISE_STOP:
            tight = candles[-1].low - 0.25 * cur_atr
            if tight > stop_loss:
                return ManageDecision(ManageAction.RAISE_STOP, new_stop=tight,
                                      reason="versnellende daling: stop onder laatste low")

        # -- 2. time-stop VÓÓR de trail: anders houden micro-verhogingen van de
        #    chandelier een dode breakout eindeloos in leven.
        if bars_held >= cfg.time_stop_bars and r_now < cfg.time_stop_min_r:
            return ManageDecision(ManageAction.EXIT_NOW,
                                  reason=f"time-stop: {bars_held} bars zonder progressie")

        # -- 3. break-even zodra +1R bereikt is.
        if not break_even_armed and r_now >= cfg.breakeven_at_r:
            be = entry_price * (1.0 + cfg.fee_pct_round_trip / 100.0)
            if be > stop_loss:
                return ManageDecision(ManageAction.RAISE_STOP, new_stop=be,
                                      reason=f"+{cfg.breakeven_at_r}R: stop naar break-even")

        # -- 4. chandelier-trail: hoogste close sinds entry − k×ATR.
        #    Altijd actief (raakt nooit lager dan de huidige stop).
        if cur_atr > 0 and bars_held > 0:
            highest = max(c.close for c in candles[-(bars_held + 1):])
            trail = highest - cfg.trail_atr_mult * cur_atr
            if trail > stop_loss:
                return ManageDecision(ManageAction.RAISE_STOP, new_stop=trail,
                                      reason=f"chandelier {cfg.trail_atr_mult}×ATR "
                                             f"onder hoogste close {highest:.6g}")

        return ManageDecision(ManageAction.HOLD, reason=f"houden ({r_now:+.2f}R)")
