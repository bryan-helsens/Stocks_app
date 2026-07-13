"""Backtest: rsi_dip_buyer v1 (baseline) vs v2 — op echte Bitvavo-candles.

Draai dit OP JE VPS (waar api.bitvavo.com bereikbaar is):

    # 60 dagen 15m-candles ophalen + beide strategieën vergelijken
    python3 backtest.py --days 60

    # alleen v2, andere universe:
    python3 backtest.py --days 90 --markets BTC-EUR,ETH-EUR,SOL-EUR --only v2

    # offline smoke-test zonder netwerk (synthetische data):
    python3 backtest.py --synthetic

Realisme dat is meegenomen (en dat v1's cijfers verklaarde):
  • fee 0.25% per zijde (Bitvavo taker)
  • stop-slippage 0.35% (jouw v1-stops vulden op −3.4% terwijl ze op −2.55%
    stonden → dat verschil is triggerd-marktverkoop-slippage)
  • gap-fills: opent een bar ónder de stop, dan vul je op de open, niet op de stop
  • entry op de open van de bar NA het signaal (geen look-ahead)
  • pessimistische intrabar-volgorde: raakt een bar stop én TP, dan telt de stop

⚠️  Educatief. Een backtest bewijst niets over de toekomst; hij falsifieert
    alleen slechte ideeën sneller dan echt geld dat doet.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import urllib.request
from dataclasses import dataclass, field

from rsi_dip_buyer_v2 import (
    Candle, CooldownTracker, CrashGuard, EntryGate, ManageAction, MarketRegime,
    PositionManager, RiskModel, StrategyConfig, atr, rsi,
)

FEE_SIDE_PCT = 0.25          # Bitvavo taker per zijde
STOP_SLIPPAGE_PCT = 0.35     # gemeten uit jouw v1-fills
DEFAULT_MARKETS = ["BTC-EUR", "ETH-EUR", "SOL-EUR", "XRP-EUR", "ADA-EUR",
                   "LTC-EUR", "AVAX-EUR", "INJ-EUR", "FET-EUR", "NEAR-EUR"]


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def fetch_bitvavo(market: str, interval: str = "15m", days: int = 60) -> list[Candle]:
    """Haalt candles op via de publieke Bitvavo-API (paginatie via `end`)."""
    ms_per = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000,
              "2h": 7_200_000, "4h": 14_400_000}[interval]
    need = days * 24 * 3600 * 1000 // ms_per
    out: list[Candle] = []
    end = int(time.time() * 1000)
    while len(out) < need:
        url = (f"https://api.bitvavo.com/v2/{market}/candles"
               f"?interval={interval}&limit=1440&end={end}")
        with urllib.request.urlopen(url, timeout=20) as r:
            rows = json.loads(r.read())
        if not rows:
            break
        rows.sort(key=lambda x: x[0])
        batch = [Candle(r0[0] / 1000, float(r0[1]), float(r0[2]),
                        float(r0[3]), float(r0[4]), float(r0[5])) for r0 in rows]
        out = batch + out
        end = rows[0][0] - 1
        time.sleep(0.25)                       # rate-limit vriendelijk
    return out[-need:]


def synthetic(days: int = 30, seed: int = 7, kind: str = "mixed") -> list[Candle]:
    """Deterministische synthetische reeks voor offline smoke-tests."""
    import random
    rng = random.Random(seed)
    n = days * 96                              # 15m-bars
    p, out = 100.0, []
    for i in range(n):
        drift = {"up": 0.0004, "down": -0.0004, "mixed":
                 0.0006 * math.sin(i / 400.0)}[kind]
        shock = -0.03 if (kind == "mixed" and i % 1500 == 1499) else 0.0
        r = rng.gauss(drift + shock, 0.011)
        o = p
        p = max(0.01, p * (1.0 + r))
        hi = max(o, p) * (1.0 + abs(rng.gauss(0, 0.004)))
        lo = min(o, p) * (1.0 - abs(rng.gauss(0, 0.004)))
        out.append(Candle(i * 900.0, o, hi, lo, p, 1.0))
    return out


# --------------------------------------------------------------------------- #
# engine
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Trade:
    symbol: str
    entry: float
    exit: float
    qty: float
    reason: str
    r_multiple: float
    net_pnl: float


@dataclass(slots=True)
class OpenPos:
    symbol: str
    entry: float
    stop: float
    tp_levels: list[tuple[float, float]]   # (prijs, fractie van ORIGINELE qty)
    qty: float                             # resterende qty
    risk_per_unit: float
    orig_qty: float = 0.0
    bars_held: int = 0
    break_even: bool = False
    realized: float = 0.0              # al gepakte partial-winst (netto)

    def __post_init__(self) -> None:
        if self.orig_qty == 0.0:
            self.orig_qty = self.qty


@dataclass
class Result:
    name: str
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    def report(self) -> str:
        t = self.trades
        if not t:
            return f"{self.name}: 0 trades"
        wins = [x.net_pnl for x in t if x.net_pnl > 0]
        losses = [x.net_pnl for x in t if x.net_pnl <= 0]
        pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float("inf")
        eq = self.equity_curve
        peak, mdd = eq[0], 0.0
        for v in eq:
            peak = max(peak, v)
            mdd = max(mdd, (peak - v) / peak)
        avg_r = statistics.mean(x.r_multiple for x in t)
        worst_r = min(x.r_multiple for x in t)
        win_rs = [x.r_multiple for x in t if x.net_pnl > 0]
        loss_rs = [x.r_multiple for x in t if x.net_pnl <= 0]
        avg_w = statistics.mean(win_rs) if win_rs else 0.0
        avg_l = statistics.mean(loss_rs) if loss_rs else 0.0
        return (f"{self.name:>4} | trades {len(t):>3} | winrate {len(wins)/len(t):5.1%} | "
                f"PF {pf:5.2f} | avgW {avg_w:+.2f}R avgL {avg_l:+.2f}R | "
                f"worst {worst_r:+.2f}R | eind €{eq[-1]:8.2f} | maxDD {mdd:5.1%}")


def _sell(price: float, qty: float, entry: float, slip_pct: float = 0.0) -> float:
    """Netto opbrengst-minus-kosten van een (deel)verkoop, incl. fees+slippage."""
    px = price * (1.0 - slip_pct / 100.0)
    gross = (px - entry) * qty
    fees = (entry * qty + px * qty) * FEE_SIDE_PCT / 100.0
    return gross - fees


def run_v2(series: dict[str, list[Candle]], btc: list[Candle],
           cfg: StrategyConfig, start_equity: float = 100.0) -> Result:
    gate, riskm = EntryGate(cfg), RiskModel(cfg)
    manager, guard = PositionManager(cfg), CrashGuard(cfg)
    cooldown = CooldownTracker(cfg)
    res = Result("v2")
    equity = start_equity
    positions: dict[str, OpenPos] = {}
    pending: dict[str, object] = {}            # signaal → entry op volgende open
    n = min(len(s) for s in series.values())
    warmup = cfg.ema_slow + 5

    for i in range(warmup, n):
        regime = guard.market_regime(btc[: i + 1][-cfg.market_window_bars - 2:])
        for sym, candles in series.items():
            window = candles[: i + 1]
            bar = window[-1]

            # ---- entry die op de vorige bar gesignaleerd is: vul op de open --
            if sym in pending and sym not in positions:
                plan = riskm.plan(sym, equity, pending.pop(sym), price=bar.open)
                if plan:
                    # koop-fee zit al in _sell() (beide zijden) — hier niets aftrekken
                    positions[sym] = OpenPos(sym, plan.entry, plan.stop,
                                             list(plan.tp_levels), plan.quantity,
                                             plan.entry - plan.stop)
            pending.pop(sym, None)

            # ---- open positie beheren --------------------------------------
            pos = positions.get(sym)
            if pos:
                pos.bars_held += 1
                risk_amt = pos.risk_per_unit * pos.orig_qty
                closed = False

                # gap-open onder de stop → vul op de open (realistisch)
                if bar.open <= pos.stop:
                    pnl = pos.realized + _sell(bar.open, pos.qty, pos.entry)
                    equity += pnl
                    res.trades.append(Trade(sym, pos.entry, bar.open, pos.qty,
                                            "gap_stop", pnl / risk_amt, pnl))
                    cooldown.record_loss_exit(sym, i)
                    del positions[sym]; closed = True
                # intrabar stop (pessimistisch vóór TP), met slippage
                elif bar.low <= pos.stop:
                    pnl = pos.realized + _sell(pos.stop, pos.qty, pos.entry,
                                               STOP_SLIPPAGE_PCT)
                    equity += pnl
                    res.trades.append(Trade(sym, pos.entry, pos.stop, pos.qty,
                                            "stop", pnl / risk_amt, pnl))
                    if pnl < 0:
                        cooldown.record_loss_exit(sym, i)
                    del positions[sym]; closed = True
                else:
                    # TP-levels (limit-fills, geen slippage); frac = fractie
                    # van de ORIGINELE positie, zoals in jouw state-model.
                    for tp_price, frac in list(pos.tp_levels):
                        if bar.high >= tp_price:
                            part_qty = min(pos.orig_qty * frac, pos.qty)
                            pnl = _sell(tp_price, part_qty, pos.entry)
                            pos.realized += pnl
                            pos.qty -= part_qty
                            pos.tp_levels.remove((tp_price, frac))
                            if not pos.tp_levels or pos.qty <= 1e-12:
                                total = pos.realized
                                equity += total
                                res.trades.append(Trade(sym, pos.entry, tp_price,
                                                        part_qty, "take_profit",
                                                        total / risk_amt, total))
                                del positions[sym]; closed = True
                                break
                            # na TP1: stop naar break-even
                            pos.stop = max(pos.stop, pos.entry)
                            pos.break_even = True

                if not closed and sym in positions:
                    d = manager.manage(entry_price=pos.entry, stop_loss=pos.stop,
                                       break_even_armed=pos.break_even,
                                       bars_held=pos.bars_held,
                                       candles=window, regime=regime)
                    if d.action is ManageAction.EXIT_NOW:
                        pnl = pos.realized + _sell(bar.close, pos.qty, pos.entry,
                                                   STOP_SLIPPAGE_PCT / 2)
                        equity += pnl
                        res.trades.append(Trade(sym, pos.entry, bar.close, pos.qty,
                                                d.reason.split(":")[0],
                                                pnl / risk_amt, pnl))
                        if pnl < 0:
                            cooldown.record_loss_exit(sym, i)
                        del positions[sym]
                    elif d.action is ManageAction.RAISE_STOP and d.new_stop:
                        pos.stop = max(pos.stop, d.new_stop)
                        if pos.stop >= pos.entry:
                            pos.break_even = True

            # ---- nieuw signaal? --------------------------------------------
            if sym not in positions and len(positions) < cfg.max_open_positions \
               and not cooldown.blocked(sym, i):
                dec = gate.evaluate(sym, window, regime=regime)
                if dec.allowed:
                    pending[sym] = dec
        res.equity_curve.append(equity)
    # open posities op het einde tegen slot waarderen
    for sym, pos in positions.items():
        last = series[sym][n - 1].close
        pnl = pos.realized + _sell(last, pos.qty, pos.entry)
        equity += pnl
        res.trades.append(Trade(sym, pos.entry, last, pos.qty, "eod",
                                pnl / (pos.risk_per_unit * pos.orig_qty), pnl))
    res.equity_curve.append(equity)
    return res


def run_v3(series: dict[str, list[Candle]], btc: list[Candle],
           cfg, start_equity: float = 100.0) -> Result:
    """v3 momentum/breakout: partial op +2R, rest op chandelier-trail.

    Zelfde realisme als run_v2 (fees, slippage, gaps, next-bar-open entry,
    stop-vóór-TP). Verschil: na de partial wordt de positie NIET gesloten —
    de rest loopt door tot de (trailing) stop of een manager-exit.
    """
    from momentum_breakout_v3 import BreakoutGate, RiskModelV3, TrailManager

    gate, riskm = BreakoutGate(cfg), RiskModelV3(cfg)
    manager, guard = TrailManager(cfg), CrashGuard(cfg)
    cooldown = CooldownTracker(cfg)
    res = Result("v3")
    equity = start_equity
    positions: dict[str, OpenPos] = {}
    pending: dict[str, object] = {}
    n = min(len(s) for s in series.values())
    warmup = max(cfg.ema_slow, cfg.breakout_lookback) + 5

    for i in range(warmup, n):
        regime = guard.market_regime(btc[: i + 1][-cfg.market_window_bars - 2:])
        for sym, candles in series.items():
            window = candles[: i + 1]
            bar = window[-1]

            if sym in pending and sym not in positions:
                plan = riskm.plan(sym, equity, pending.pop(sym), price=bar.open)
                if plan:
                    positions[sym] = OpenPos(sym, plan.entry, plan.stop,
                                             list(plan.tp_levels), plan.quantity,
                                             plan.entry - plan.stop)
            pending.pop(sym, None)

            pos = positions.get(sym)
            if pos:
                pos.bars_held += 1
                risk_amt = pos.risk_per_unit * pos.orig_qty
                closed = False

                if bar.open <= pos.stop:                     # gap onder stop
                    pnl = pos.realized + _sell(bar.open, pos.qty, pos.entry)
                    equity += pnl
                    res.trades.append(Trade(sym, pos.entry, bar.open, pos.qty,
                                            "gap_stop", pnl / risk_amt, pnl))
                    if pnl < 0:
                        cooldown.record_loss_exit(sym, i)
                    del positions[sym]; closed = True
                elif bar.low <= pos.stop:                    # intrabar stop
                    pnl = pos.realized + _sell(pos.stop, pos.qty, pos.entry,
                                               STOP_SLIPPAGE_PCT)
                    equity += pnl
                    reason = "trail_stop" if pos.stop > pos.entry else "stop"
                    res.trades.append(Trade(sym, pos.entry, pos.stop, pos.qty,
                                            reason, pnl / risk_amt, pnl))
                    if pnl < 0:
                        cooldown.record_loss_exit(sym, i)
                    del positions[sym]; closed = True
                else:
                    # partial TP (limit-fill); positie blijft daarna open!
                    for tp_price, frac in list(pos.tp_levels):
                        if bar.high >= tp_price:
                            part_qty = min(pos.orig_qty * frac, pos.qty)
                            pos.realized += _sell(tp_price, part_qty, pos.entry)
                            pos.qty -= part_qty
                            pos.tp_levels.remove((tp_price, frac))
                            pos.stop = max(pos.stop, pos.entry)
                            pos.break_even = True

                if not closed and sym in positions:
                    d = manager.manage(entry_price=pos.entry, stop_loss=pos.stop,
                                       break_even_armed=pos.break_even,
                                       bars_held=pos.bars_held,
                                       candles=window, regime=regime)
                    if d.action is ManageAction.EXIT_NOW:
                        pnl = pos.realized + _sell(bar.close, pos.qty, pos.entry,
                                                   STOP_SLIPPAGE_PCT / 2)
                        equity += pnl
                        res.trades.append(Trade(sym, pos.entry, bar.close,
                                                pos.qty, d.reason.split(":")[0],
                                                pnl / risk_amt, pnl))
                        if pnl < 0:
                            cooldown.record_loss_exit(sym, i)
                        del positions[sym]
                    elif d.action is ManageAction.RAISE_STOP and d.new_stop:
                        pos.stop = max(pos.stop, d.new_stop)
                        if pos.stop >= pos.entry:
                            pos.break_even = True

            if sym not in positions and len(positions) < cfg.max_open_positions \
               and not cooldown.blocked(sym, i):
                dec = gate.evaluate(sym, window, regime=regime)
                if dec.allowed:
                    pending[sym] = dec
        res.equity_curve.append(equity)

    for sym, pos in positions.items():
        last = series[sym][n - 1].close
        pnl = pos.realized + _sell(last, pos.qty, pos.entry)
        equity += pnl
        res.trades.append(Trade(sym, pos.entry, last, pos.qty, "eod",
                                pnl / (pos.risk_per_unit * pos.orig_qty), pnl))
    res.equity_curve.append(equity)
    return res


def run_v1(series: dict[str, list[Candle]], start_equity: float = 100.0) -> Result:
    """Baseline die v1 nabootst: RSI<30 → koop, stop −2.55%, TP +2.45%,
    geen trendfilter, geen cooldown, geen interceptor (gemeten uit state.json)."""
    res = Result("v1")
    equity = start_equity
    positions: dict[str, OpenPos] = {}
    n = min(len(s) for s in series.values())
    warmup = 20

    for i in range(warmup, n):
        for sym, candles in series.items():
            window = candles[: i + 1]
            bar = window[-1]
            pos = positions.get(sym)
            if pos:
                risk_amt = pos.risk_per_unit * pos.orig_qty
                if bar.open <= pos.stop or bar.low <= pos.stop:
                    fill = bar.open if bar.open <= pos.stop else pos.stop
                    pnl = _sell(fill, pos.qty, pos.entry, STOP_SLIPPAGE_PCT)
                    equity += pnl
                    res.trades.append(Trade(sym, pos.entry, fill, pos.qty, "stop",
                                            pnl / risk_amt, pnl))
                    del positions[sym]
                elif bar.high >= pos.tp_levels[0][0]:
                    tp = pos.tp_levels[0][0]
                    pnl = _sell(tp, pos.qty, pos.entry)
                    equity += pnl
                    res.trades.append(Trade(sym, pos.entry, tp, pos.qty,
                                            "take_profit", pnl / risk_amt, pnl))
                    del positions[sym]
            elif len(positions) < 6:           # v1 hield tot 6 posities open
                rs = rsi([c.close for c in window], 14)
                if rs and rs[-1] < 30.0:
                    entry = bar.close
                    stop = entry * (1 - 0.0255)
                    tp = entry * (1 + 0.0245)
                    stake = equity * 0.12      # v1 zette ~€11.4 per trade op €95
                    qty = stake / entry
                    # koop-fee zit al in _sell() (beide zijden) — niet dubbel tellen
                    positions[sym] = OpenPos(sym, entry, stop, [(tp, 1.0)], qty,
                                             entry - stop)
        res.equity_curve.append(equity)
    for sym, pos in positions.items():
        last = series[sym][n - 1].close
        pnl = _sell(last, pos.qty, pos.entry)
        equity += pnl
        res.trades.append(Trade(sym, pos.entry, last, pos.qty, "eod",
                                pnl / (pos.risk_per_unit * pos.orig_qty), pnl))
    res.equity_curve.append(equity)
    return res


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--interval", default="15m",
                    choices=["5m", "15m", "1h", "2h", "4h"])
    ap.add_argument("--markets", default=",".join(DEFAULT_MARKETS))
    ap.add_argument("--only", choices=["v1", "v2", "v3"], default=None)
    ap.add_argument("--maker", action="store_true",
                    help="reken met limit-order (maker) fees: 0.15%%/zijde "
                         "i.p.v. 0.25%% taker")
    ap.add_argument("--synthetic", action="store_true",
                    help="offline smoke-test zonder netwerk")
    args = ap.parse_args()

    markets = [m.strip() for m in args.markets.split(",") if m.strip()]
    series: dict[str, list[Candle]] = {}
    if args.synthetic:
        kinds = ["mixed", "up", "down", "mixed", "up"]
        for i, m in enumerate(markets[:5]):
            series[m] = synthetic(days=args.days, seed=11 + i,
                                  kind=kinds[i % len(kinds)])
        btc = series.get("BTC-EUR") or next(iter(series.values()))
        print(f"[synthetic] {len(series)} markten × {args.days} dagen")
    else:
        for m in markets:
            print(f"fetch {m} …", flush=True)
            series[m] = fetch_bitvavo(m, args.interval, args.days)
        btc = series.get("BTC-EUR") or fetch_bitvavo("BTC-EUR", args.interval, args.days)

    global FEE_SIDE_PCT
    if args.maker:
        FEE_SIDE_PCT = 0.15
    cfg = StrategyConfig(fee_pct_round_trip=2 * FEE_SIDE_PCT)
    print(f"\n=== resultaat (start €100, fees {FEE_SIDE_PCT}%/zijde, "
          f"stop-slippage {STOP_SLIPPAGE_PCT}%) ===")
    if args.only in (None, "v1"):
        print(run_v1(series).report())
    if args.only in (None, "v2"):
        print(run_v2(series, btc, cfg).report())
    if args.only in (None, "v3"):
        from momentum_breakout_v3 import BreakoutConfig
        cfg3 = BreakoutConfig(fee_pct_round_trip=2 * FEE_SIDE_PCT)
        print(run_v3(series, btc, cfg3).report())
    print("\n⚠️  backtest ≠ toekomst; gebruik dit om ideeën te falsifiëren, "
          "niet om winst te voorspellen.")


if __name__ == "__main__":
    main()
